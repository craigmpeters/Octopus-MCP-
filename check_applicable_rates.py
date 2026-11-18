"""Run a one-day, read-only Kraken probe from the configured container."""
import argparse
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import server


QUERY = """
query CheckApplicableRates($account: String!, $point: String!, $start: DateTime!, $end: DateTime!) {
  applicableRates(accountNumber: $account, mpxn: $point, startAt: $start, endAt: $end, first: 100) {
    pageInfo { hasNextPage }
    edges { node { value validFrom validTo } }
  }
}
"""


def summarize(connection, start, end):
    try:
        edges = connection['edges']
        has_next_page = connection['pageInfo']['hasNextPage']
    except (KeyError, TypeError):
        raise ValueError('Kraken did not return an applicableRates page.') from None
    if not isinstance(edges, list) or not isinstance(has_next_page, bool):
        raise ValueError('Kraken returned an invalid applicableRates page.')

    values, intervals = set(), []
    invalid = outside = half_hours = 0
    for edge in edges:
        try:
            node = edge['node']
            interval_start = server.parse_api_datetime(node['validFrom'])
            interval_end = server.parse_api_datetime(node['validTo'])
            value = Decimal(str(node['value']))
            if (interval_start is None or interval_end is None or interval_end <= interval_start
                    or not value.is_finite()):
                raise ValueError
        except (KeyError, TypeError, ValueError, InvalidOperation):
            invalid += 1
            continue
        if interval_end <= start or interval_start >= end:
            outside += 1
            continue
        values.add(value)
        if interval_end - interval_start == timedelta(minutes=30):
            half_hours += 1
        intervals.append((max(start, interval_start), min(end, interval_end)))

    covered = timedelta()
    overlapping = 0
    covered_end = start
    for interval_start, interval_end in sorted(intervals):
        if interval_start < covered_end:
            overlapping += 1
        if interval_end > covered_end:
            covered += interval_end - max(interval_start, covered_end)
            covered_end = interval_end

    return {
        'rows_on_first_page': len(edges),
        'has_more_pages': has_next_page,
        'rows_intersecting_day': len(intervals),
        'half_hour_rows_intersecting_day': half_hours,
        'distinct_values_in_day': len(values),
        'rows_outside_day': outside,
        'rows_missing_valid_bounds_or_value': invalid,
        'overlapping_rows_in_day': overlapping,
        'covered_minutes_in_day': covered.total_seconds() / 60,
        'minutes_in_day': (end - start).total_seconds() / 60,
    }


def check_applicable_rates(day):
    start, end = server.uk_date_window(day, day)
    try:
        inventory = server.list_meters()
    except (ValueError, AttributeError, TypeError):
        raise ValueError('Could not discover the configured account’s supply points.') from None
    import_points = [point['meter_point'] for point in inventory['supply_points']
                     if point['direction'] == 'import' and point['meter_point']]
    if len(import_points) != 1:
        raise ValueError('The check requires exactly one electricity import supply point.')
    try:
        token = server.graphql_token()
    except ValueError:
        raise ValueError('Kraken token exchange failed.') from None
    try:
        data = server.graphql_request(QUERY, {
            'account': server.ACCOUNT, 'point': import_points[0],
            'start': start.isoformat(), 'end': end.isoformat(),
        }, token)
    except ValueError:
        raise ValueError('Kraken applicableRates query failed after token exchange.') from None
    return summarize(data.get('applicableRates'), start, end)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('day', metavar='YYYY-MM-DD', help='UK date to check')
    args = parser.parse_args()
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    try:
        result = check_applicable_rates(args.day)
    except (ValueError, OverflowError) as exc:
        parser.exit(1, f'{exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
