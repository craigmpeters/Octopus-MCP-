from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest
import server


def interval(start):
    return {'interval_start': start.isoformat(), 'interval_end': (start + timedelta(minutes=30)).isoformat(), 'consumption': 1}


@pytest.mark.parametrize(('day', 'count'), [('2025-03-30', 46), ('2025-10-26', 50), ('2025-02-01', 48)])
def test_uk_day_and_pagination(day, count):
    local = datetime.combine(date.fromisoformat(day), time.min, ZoneInfo('Europe/London'))
    start = local.astimezone(timezone.utc)
    records = [interval(start + timedelta(minutes=30 * n)) for n in range(count)]
    pages = [{'results': list(reversed(records[20:])), 'next': 'https://api.octopus.energy/v1/next'},
             {'results': records[:20] + [interval(start + timedelta(minutes=30 * count))], 'next': None}]
    supply = [{'fuel': 'electricity', 'meter_point': '123', 'serial_number': 'abc'}]
    with patch.object(server, 'supplies', return_value=supply), patch.object(server, 'get', side_effect=pages) as get:
        result = server.consumption('electricity', '123', 'abc', day, day)
    assert result['records'] == records
    assert result['record_count'] == count
    assert result['coverage'] == {
        'interval_minutes': 30,
        'expected_interval_count': count,
        'returned_interval_count': count,
        'missing_interval_count': 0,
        'complete': True,
        'gaps': [],
    }
    assert get.call_args_list[0].args[1]['period_from'] == start.isoformat()
    assert get.call_args_list[1].args[1] is None


def test_duplicate_intervals_rejected():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='Duplicate'):
        server.filter_consumption_records([interval(start), interval(start)], start, start + timedelta(days=1))


def test_invalid_interval_rejected():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='Invalid'):
        server.filter_consumption_records([{'interval_start': 'bad'}], start, start + timedelta(days=1))


def test_unowned_meter_rejected():
    with patch.object(server, 'supplies', return_value=[]), pytest.raises(ValueError, match='belong'):
        server.consumption('gas', '123', 'abc', '2025-01-01', '2025-01-01')


def test_coverage_reports_consecutive_missing_intervals_as_one_gap():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    records = [interval(start + timedelta(minutes=30 * n)) for n in range(48) if n not in (3, 4, 20)]
    coverage = server.consumption_coverage(records, start, start + timedelta(days=1))
    assert coverage['expected_interval_count'] == 48
    assert coverage['returned_interval_count'] == 45
    assert coverage['missing_interval_count'] == 3
    assert coverage['complete'] is False
    assert coverage['gaps'] == [
        {'interval_start': '2025-01-01T01:30:00+00:00', 'interval_end': '2025-01-01T02:30:00+00:00', 'missing_interval_count': 2},
        {'interval_start': '2025-01-01T10:00:00+00:00', 'interval_end': '2025-01-01T10:30:00+00:00', 'missing_interval_count': 1},
    ]


def test_coverage_rejects_non_half_hour_interval():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    record = {'interval_start': start.isoformat(), 'interval_end': (start + timedelta(hours=1)).isoformat(), 'consumption': 1}
    with pytest.raises(ValueError, match='half-hour'):
        server.consumption_coverage([record], start, start + timedelta(days=1))


def test_default_order_pagination_filters_boundary_and_sorts():
    start = datetime(2026, 11, 8, tzinfo=timezone.utc)
    records = [interval(start + timedelta(minutes=30 * n)) for n in range(337)]
    descending = list(reversed(records))
    pages = [{'results': descending[:250], 'next': 'https://api.octopus.energy/v1/next?page=2'},
             {'results': descending[250:], 'next': None}]
    supply = [{'fuel': 'electricity', 'meter_point': '123', 'serial_number': 'abc'}]
    with patch.object(server, 'supplies', return_value=supply), patch.object(server, 'get', side_effect=pages) as get:
        result = server.consumption('electricity', '123', 'abc', '2026-11-08', '2026-11-14')
    assert get.call_count == 2
    assert 'order_by' not in get.call_args_list[0].args[1]
    assert get.call_args_list[1].args == ('https://api.octopus.energy/v1/next?page=2', None)
    assert result['records'] == records[:336]
