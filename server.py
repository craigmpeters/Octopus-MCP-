"""Personal, local-only, read-only Octopus Energy MCP server."""
import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo
import httpx
from mcp.server.fastmcp import FastMCP

API = 'https://api.octopus.energy/v1/'
KEY = os.getenv('OCTOPUS_API_KEY', '')
ACCOUNT = os.getenv('OCTOPUS_ACCOUNT_NUMBER', '')
mcp = FastMCP('Personal Octopus Energy', host='0.0.0.0', port=8000, stateless_http=True, json_response=True)

def get(path, params=None):
    if not KEY or not ACCOUNT:
        raise ValueError('Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT_NUMBER on the server.')
    url = path if path.startswith('https://') else API + path.lstrip('/')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('api.octopus.energy', 'api.oegb-kraken.energy') or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Unexpected API pagination URL')
    try:
        with httpx.Client(auth=(KEY, ''), timeout=30, follow_redirects=False) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f'Octopus API returned HTTP {exc.response.status_code}; check account, access and requested data.') from None
    except httpx.RequestError:
        raise ValueError('Unable to reach the Octopus API; try again later.') from None

def account():
    return get('accounts/' + quote(ACCOUNT, safe='') + '/')

def supplies():
    out = []
    for prop in account().get('properties', []):
        for fuel, key, identifier in [('electricity', 'electricity_meter_points', 'mpan'), ('gas', 'gas_meter_points', 'mprn')]:
            for point in prop.get(key, []):
                for meter in point.get('meters', []):
                    out.append({'fuel': fuel, 'meter_point': str(point.get(identifier, '')), 'serial_number': meter.get('serial_number'), 'agreements': point.get('agreements', []), 'is_export': point.get('is_export', False)})
    return out

@mcp.tool()
def list_meters() -> dict:
    """List account meters and known tariff agreements; identifies import/export where available."""
    return {'meters': supplies(), 'note': 'Account history can include old meters and tariffs. Select the relevant meter and dates.'}

def filter_consumption_records(records, window_start, window_end):
    """Keep intervals fully inside [start, end), in chronological order."""
    filtered = []
    seen = set()
    for record in records:
        try:
            start = datetime.fromisoformat(record['interval_start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(record['interval_end'].replace('Z', '+00:00'))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError('Invalid timestamp in Octopus consumption response') from None
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError('Invalid interval in Octopus consumption response')
        if window_start <= start and end <= window_end:
            identity = (start, end)
            if identity in seen:
                raise ValueError('Duplicate interval in Octopus consumption response')
            seen.add(identity)
            filtered.append(record)
    return sorted(filtered, key=lambda record: datetime.fromisoformat(record['interval_start'].replace('Z', '+00:00')))

@mcp.tool()
def consumption(fuel: str, meter_point: str, serial_number: str, start_date: str, end_date: str) -> dict:
    """Get meter consumption for inclusive UK dates YYYY-MM-DD, up to 31 days. Use list_meters first. Data can be delayed or missing; gas units may be m3."""
    if fuel not in ('electricity', 'gas'):
        raise ValueError('fuel must be electricity or gas')
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 30:
        raise ValueError('Use an inclusive date range of at most 31 days')
    if not any(s['fuel'] == fuel and s['meter_point'] == meter_point and s['serial_number'] == serial_number for s in supplies()):
        raise ValueError('Meter does not belong to the configured account')
    tz = ZoneInfo('Europe/London')
    begin = datetime.combine(start, datetime.min.time(), tz).astimezone(timezone.utc).isoformat()
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tz).astimezone(timezone.utc).isoformat()
    records = []
    # Keep requests below the normal page size: multi-day pagination has returned
    # duplicate intervals in live use. Still follow pagination if an API page
    # is unexpectedly short, and validate the combined response below.
    for day_offset in range((end - start).days + 1):
        day = start + timedelta(days=day_offset)
        day_start = datetime.combine(day, datetime.min.time(), tz).astimezone(timezone.utc)
        day_end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tz).astimezone(timezone.utc)
        path = f'{fuel}-meter-points/{quote(meter_point, safe="")}/meters/{quote(serial_number, safe="")}/consumption/'
        params = {'period_from': day_start.isoformat(), 'period_to': day_end.isoformat(), 'page_size': 250, 'order_by': 'period'}
        day_records = []
        for _ in range(20):
            data = get(path, params)
            day_records.extend(data.get('results', []))
            path = data.get('next')
            if not path:
                break
            params = None
        else:
            raise ValueError('Too many consumption pages for one day')
        # The API may include an interval at period_to. Filter per day so it
        # cannot be duplicated by the following day's request.
        records.extend(filter_consumption_records(day_records, day_start, day_end))
    # Octopus can return a reading starting at the exclusive period_to boundary.
    # Filter it out, while preserving legitimate short/long DST days.
    window_start = datetime.fromisoformat(begin)
    window_end = datetime.fromisoformat(finish)
    records = filter_consumption_records(records, window_start, window_end)
    return {'fuel': fuel, 'start_date': start_date, 'end_date_inclusive': end_date, 'records': records, 'record_count': len(records), 'unit_note': 'Electricity kWh; gas may be m³ or kWh depending on meter. Confirm before calculating cost.', 'coverage_note': 'Missing or delayed intervals are not zero; dates converted from Europe/London. Returned intervals are sorted and restricted to the requested date window.'}

@mcp.tool()
def tariff_rates(product_code: str, tariff_code: str, fuel: str, start_date: str, end_date: str) -> dict:
    """Fetch standard unit rates and standing charges for a product and tariff, inclusive UK dates, up to 31 days. Economy 7 or special tariff rates may require other endpoints."""
    if fuel not in ('electricity', 'gas'):
        raise ValueError('fuel must be electricity or gas')
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end-start).days > 30:
        raise ValueError('Use at most 31 inclusive days')
    tz = ZoneInfo('Europe/London')
    params = {'period_from': datetime.combine(start, datetime.min.time(), tz).astimezone(timezone.utc).isoformat(), 'period_to': datetime.combine(end+timedelta(days=1), datetime.min.time(), tz).astimezone(timezone.utc).isoformat(), 'page_size': 250}
    base = f'products/{quote(product_code, safe="")}/{fuel}-tariffs/{quote(tariff_code, safe="")}/'
    result = {}
    for kind in ('standard-unit-rates', 'standing-charges'):
        path, query, rows = base + kind + '/', params, []
        for _ in range(20):
            page = get(path, query)
            rows.extend(page.get('results', []))
            path, query = page.get('next'), None
            if not path:
                break
        else:
            raise ValueError('Too many tariff pages; request a shorter period')
        result[kind] = rows
    return {'rates': result, 'note': 'Rates are in pence; use VAT-inclusive values. Standard rates may not capture EV dispatch, export, dual-rate, discounts or actual bills.'}

if __name__ == '__main__':
    mcp.run(transport='streamable-http')
