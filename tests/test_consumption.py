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
