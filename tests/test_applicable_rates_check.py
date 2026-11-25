import json
import sys

import httpx
import pytest

import check_applicable_rates as check
import server


def test_check_uses_configured_account_and_prints_aggregate_only(monkeypatch, capsys):
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'properties': [{'electricity_meter_points': [
                {'mpan': 'private-import', 'meters': [{'serial_number': 'old'}, {'serial_number': 'new'}]},
                {'mpan': 'private-export', 'is_export': True},
            ]}]})
        if len(requests) == 2:
            return httpx.Response(200, json={'data': {'obtainKrakenToken': {'token': 'synthetic-token'}}})
        return httpx.Response(200, json={'data': {'applicableRates': {
            'pageInfo': {'hasNextPage': True},
            'edges': [
                {'node': {'validFrom': '2025-10-25T23:00:00Z', 'validTo': '2025-10-25T23:30:00Z', 'value': '12.3'}},
                {'node': {'validFrom': '2025-10-25T23:15:00Z', 'validTo': '2025-10-25T23:45:00Z', 'value': '12.30'}},
                {'node': {'validFrom': '2025-10-27T00:00:00Z', 'validTo': '2025-10-27T00:30:00Z', 'value': '12.3'}},
                {'node': {'validFrom': None, 'validTo': None, 'value': '12.3'}},
            ],
        }}})

    client = httpx.Client
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(server.httpx, 'Client', lambda **kwargs: client(transport=transport, **kwargs))
    monkeypatch.setattr(server, 'KEY', 'synthetic-key')
    monkeypatch.setattr(server, 'ACCOUNT', 'private-account')
    monkeypatch.setattr(sys, 'argv', ['check_applicable_rates.py', '2025-10-26'])

    check.main()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        'rows_on_first_page': 4, 'has_more_pages': True, 'rows_intersecting_day': 2,
        'half_hour_rows_intersecting_day': 2, 'distinct_values_in_day': 1, 'rows_outside_day': 1,
        'rows_missing_valid_bounds_or_value': 1, 'overlapping_rows_in_day': 1,
        'minutes_with_multiple_distinct_values': 0, 'covered_minutes_in_day': 45, 'minutes_in_day': 1500,
    }
    assert not captured.err
    assert str(requests[1].url) == str(requests[2].url) == server.GRAPHQL_API
    assert requests[1].headers.get('Authorization') is None
    assert requests[2].headers['Authorization'] == 'synthetic-token'
    assert json.loads(requests[2].content)['variables'] == {
        'account': 'private-account', 'point': 'private-import',
        'start': '2025-10-25T23:00:00+00:00', 'end': '2025-10-27T00:00:00+00:00',
    }


def test_check_reports_query_failure_without_upstream_details(monkeypatch):
    monkeypatch.setattr(server, 'list_meters', lambda: {
        'supply_points': [{'direction': 'import', 'meter_point': 'private-import'}],
    })
    monkeypatch.setattr(server, 'graphql_token', lambda: 'synthetic-token')

    def fail(*args):
        raise ValueError('upstream error for private-import')

    monkeypatch.setattr(server, 'graphql_request', fail)
    with pytest.raises(ValueError, match=r'^Kraken applicableRates query failed after token exchange\.$'):
        check.check_applicable_rates('2025-10-26')


def test_check_requires_one_import_supply_before_token_exchange(monkeypatch):
    monkeypatch.setattr(server, 'list_meters', lambda: {'supply_points': [
        {'direction': 'import', 'meter_point': 'one'},
        {'direction': 'import', 'meter_point': 'two'},
    ]})
    monkeypatch.setattr(server, 'graphql_token', lambda: pytest.fail('unexpected token exchange'))

    with pytest.raises(ValueError, match='exactly one electricity import supply point'):
        check.check_applicable_rates('2025-10-26')


def test_distinct_value_overlap_counts_each_minute_once_within_window():
    start, end = server.uk_date_window('2026-01-01', '2026-01-01')
    rows = [
        ('2025-12-31T23:30Z', '2026-01-01T01:00Z', '1'),
        ('2025-12-31T23:45Z', '2026-01-01T00:30Z', '1.0'),
        ('2025-12-31T23:50Z', '2026-01-01T00:45Z', '2'),
        ('2026-01-01T00:15Z', '2026-01-01T00:35Z', '3'),
        ('2026-01-01T01:00Z', '2026-01-02T00:30Z', '4'),
        ('2026-01-01T23:45Z', '2026-01-02T00:45Z', '5'),
    ]
    page = {
        'pageInfo': {'hasNextPage': False},
        'edges': [{'node': {'validFrom': a, 'validTo': b, 'value': value}}
                  for a, b, value in reversed(rows)],
    }
    summary = check.summarize(page, start, end)
    assert summary['minutes_with_multiple_distinct_values'] == 60
