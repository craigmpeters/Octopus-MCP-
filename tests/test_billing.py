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
            assert variables == {'account': 'test-account', 'start': '2025-10-25T23:00:00+00:00'}
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
    assert calls[-1][1] == {'id': '21', 'after': 'prior', 'start': '2025-10-25T23:00:00+00:00'}


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
