import pytest

import server


@pytest.fixture
def upstream(monkeypatch):
    agreements = [{'id': 21, 'valid_from': '2025-01-01T00:00Z', 'valid_to': None}]
    point = {'direction': 'IMPORT', 'mpan': 'test-point', 'agreements': agreements}
    row = {'startAt': '2025-10-25T23:00Z', 'endAt': '2025-10-26T01:00Z',
           'numberOfUnits': '1.00', 'netAmount': '0.25', 'settlementUnit': 'kWh',
           'itemType': 'CONSUMPTION_CHARGE'}
    page = {'edges': [{'node': row}], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}
    calls = []

    def request(query, variables, token):
        assert token == 'mock-token'
        calls.append((query, variables))
        if query == server.BILLING_AGREEMENTS:
            assert variables['account'] == 'test-account'
            return {'account': {'properties': [{'electricityMeterPoints': [point]}]}}
        assert query == server.BILLING_ITEMS
        return {'electricityAgreement': {'lineItems': page}}

    monkeypatch.setattr(server, 'ACCOUNT', 'test-account')
    monkeypatch.setattr(server, 'graphql_token', lambda: 'mock-token')
    monkeypatch.setattr(server, 'graphql_request', request)
    return point, page, calls


def test_billing_preserves_upstream_period_and_decimals(upstream):
    _, page, calls = upstream
    row = page['edges'][0]['node']
    page['edges'].append({'node': dict(row, startAt='2025-10-27T00:00Z', endAt='2025-10-27T00:30Z')})
    page['pageInfo'] = {'hasNextPage': True, 'endCursor': 'next'}
    result = server.billing('test-point', '2025-10-26', '21', 'prior')
    assert result['records'] == [row]
    assert result['next_cursor'] == 'next'
    assert calls[-1][1] == {'id': '21', 'after': 'prior', 'grouping': 'HALF_HOUR',
                            'start': '2025-10-25T23:00:00+00:00'}


@pytest.mark.parametrize('direction,agreement', [('IMPORT', 'other'), ('EXPORT', '21')])
def test_billing_requires_account_import_agreement(upstream, direction, agreement):
    point, _, calls = upstream
    point['direction'] = direction
    with pytest.raises(ValueError, match='No matching import agreement'):
        server.billing('test-point', '2025-10-26', agreement)
    assert len(calls) == 1


def test_overlapping_agreements_require_selection(upstream):
    point, _, calls = upstream
    point['agreements'].append(dict(point['agreements'][0], id=22))
    assert server.billing('test-point', '2025-10-26') == {
        'status': 'select_agreement', 'agreement_ids': ['21', '22']}
    assert len(calls) == 1


def test_empty_page_and_malformed_page_are_distinct(upstream):
    _, page, _ = upstream
    page['edges'] = []
    assert server.billing('test-point', '2025-10-26')['records'] == []
    page['pageInfo']['hasNextPage'] = True
    with pytest.raises(ValueError, match='incomplete billing line'):
        server.billing('test-point', '2025-10-26')


@pytest.mark.parametrize(('month', 'last', 'exclusive'), [
    ('2024-02', '2024-02-29', '2024-03-01'),
    ('2025-02', '2025-02-28', '2025-03-01'),
    ('2026-12', '2026-12-31', '2027-01-01'),
])
def test_monthly_issued_bills(monkeypatch, month, last, exclusive):
    first = month + '-01'
    bills = [{'billType': 'INVOICE', 'issuedDate': issued, 'fromDate': '2023-11-05',
              'toDate': '2023-12-05', 'grossAmountPence': 1234}
             for issued in (first, month + '-15', last, exclusive)]
    def request(query, variables, token):
        assert query == server.ISSUED_BILLS
        assert 'includeInvoices: true' in query
        assert token == 'mock-token'
        assert variables == {'account': 'test-account', 'start': first, 'end': exclusive, 'after': 'page1'}
        return {'account': {'bills': {'edges': [{'node': bill} for bill in bills],
                                     'pageInfo': {'hasNextPage': True, 'endCursor': 'page2'}}}}

    monkeypatch.setattr(server, 'ACCOUNT', 'test-account')
    monkeypatch.setattr(server, 'graphql_token', lambda: 'mock-token')
    monkeypatch.setattr(server, 'graphql_request', request)
    result = server.billing(month=month, after='page1')
    assert result['records'] == bills[:3]
    assert result['start_date'] == first
    assert result['end_date_inclusive'] == last
    assert result['next_cursor'] == 'page2'


def test_monthly_meter_lines_use_uk_month_and_preserve_cross_boundary_rows(upstream):
    point, page, calls = upstream
    point['agreements'][0]['valid_from'] = '2025-10-12T00:00Z'
    template = page['edges'][0]['node']
    rows = [dict(template, startAt=start, endAt=end) for start, end in [
        ('2025-10-12T00:00Z', '2025-10-22T00:00Z'),
        ('2025-10-31T23:00Z', '2025-11-02T00:00Z'),
        ('2025-11-01T00:00Z', '2025-12-01T00:00Z'),
    ]]
    page['edges'] = [{'node': row} for row in rows]
    result = server.billing(month='2025-10', meter_point='test-point')
    assert result['records'] == rows[:2]
    assert calls[0][1]['start'] == calls[1][1]['start'] == '2025-09-30T23:00:00+00:00'
    assert calls[1][1]['grouping'] == 'MONTH'


@pytest.mark.parametrize('params', [
    {}, {'month': '2026-13'}, {'month': '2026-1'}, {'month': '2026-10', 'day': '2026-10-01'},
    {'month': '2026-10', 'agreement_id': '42'}, {'month': '2026-10', 'after': ''},
])
def test_bad_monthly_request_stops_before_authentication(monkeypatch, params):
    monkeypatch.setattr(server, 'graphql_token', lambda: pytest.fail('unexpected token request'))
    with pytest.raises(ValueError):
        server.billing(**params)
