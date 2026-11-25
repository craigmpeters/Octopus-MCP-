"""Personal, local-only, read-only Octopus Energy MCP server."""
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo
import httpx
from mcp.server.fastmcp import FastMCP

API = 'https://api.octopus.energy/v1/'
REST_ORIGIN = httpx.URL(API)
GRAPHQL_API = 'https://api.oegb-kraken.energy/v1/graphql/'
KEY = os.getenv('OCTOPUS_API_KEY', '')
ACCOUNT = os.getenv('OCTOPUS_ACCOUNT_NUMBER', '')
REST_REQUEST_LIMIT = 40
REST_RESPONSE_BYTES = 2 * 1024 * 1024
REST_TOTAL_BYTES = 8 * 1024 * 1024
REST_TIME_BUDGET = 45
HTTP_TIMEOUT = 30
UK_TIMEZONE = ZoneInfo('Europe/London')
TARIFF_IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,100}')
mcp = FastMCP('Personal Octopus Energy', host='0.0.0.0', port=8000, stateless_http=True, json_response=True)

class OctopusREST:
    """Own one HTTP client and a shared REST budget for a single tool call."""

    def __init__(self):
        self.client = httpx.Client(
            auth=(KEY, ''), follow_redirects=False, headers={'Accept-Encoding': 'identity'},
        )
        self.requests_left = REST_REQUEST_LIMIT
        self.bytes_left = REST_TOTAL_BYTES
        self.deadline = monotonic() + REST_TIME_BUDGET

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.client.close()

    def remaining_time(self):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise ValueError('Octopus API time budget exceeded. Narrow the request.')
        return remaining

    def get(self, path, params=None):
        if not KEY or not ACCOUNT:
            raise ValueError('Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT_NUMBER on the server.')
        try:
            url = httpx.URL(urljoin(API, path))
        except (ValueError, TypeError, httpx.InvalidURL):
            raise ValueError('Unexpected API pagination URL') from None
        if (url.scheme != REST_ORIGIN.scheme or url.host != REST_ORIGIN.host
                or url.port != REST_ORIGIN.port or url.userinfo):
            raise ValueError('Unexpected API pagination URL')
        if self.requests_left == 0:
            raise ValueError('Octopus API request budget exceeded. Narrow the request.')
        if self.bytes_left == 0:
            raise ValueError('Octopus API response budget exceeded. Narrow the request.')
        self.requests_left -= 1
        timeout = min(HTTP_TIMEOUT, self.remaining_time())
        try:
            with self.client.stream('GET', url, params=params, timeout=timeout) as response:
                response.raise_for_status()
                self.remaining_time()
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise ValueError('Unexpected encoding in Octopus API response')
                body = bytearray()
                for chunk in response.iter_bytes():
                    self.remaining_time()
                    if len(chunk) > self.bytes_left:
                        raise ValueError('Octopus API response budget exceeded. Narrow the request.')
                    if len(body) + len(chunk) > REST_RESPONSE_BYTES:
                        raise ValueError('Octopus API response is too large')
                    self.bytes_left -= len(chunk)
                    body.extend(chunk)
                self.remaining_time()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f'Octopus API returned HTTP {exc.response.status_code}; check account, access and requested data.') from None
        except httpx.RequestError:
            raise ValueError('Unable to reach the Octopus API; try again later.') from None
        try:
            return json.loads(body)
        except (ValueError, RecursionError):
            raise ValueError('Octopus API returned invalid JSON') from None

def paginated_results(rest, path, params):
    """Collect a paginated REST collection or fail without returning partial results."""
    rows, seen = [], set()
    for _ in range(20):
        page = rest.get(path, params)
        if not isinstance(page, dict) or not isinstance(page.get('results'), list):
            raise ValueError('Octopus API page is missing a valid results list')
        rows.extend(page['results'])
        path = page.get('next')
        if path is None:
            return rows
        if not isinstance(path, str) or not path.strip() or path in seen:
            raise ValueError('Invalid Octopus API pagination continuation')
        seen.add(path)
        params = None
    raise ValueError('Too many Octopus API pages. Narrow the request.')

def account(rest):
    return rest.get('accounts/' + quote(ACCOUNT, safe='') + '/')

def graphql_request(query, variables, token=None):
    if not KEY or not ACCOUNT:
        raise ValueError('Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT_NUMBER on the server.')
    headers = {'Authorization': token} if token else None
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
            response = client.post(GRAPHQL_API, headers=headers, json={'query': query, 'variables': variables})
            response.raise_for_status()
            payload = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        raise ValueError('Unable to retrieve Octopus GraphQL metadata') from None
    if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('data'), dict):
        raise ValueError('Unable to retrieve Octopus GraphQL metadata')
    return payload['data']

def graphql_token():
    token_data = graphql_request(
        'mutation ObtainToken($input: ObtainJSONWebTokenInput!) '
        '{ obtainKrakenToken(input: $input) { token } }',
        {'input': {'APIKey': KEY}},
    )
    try:
        token = token_data['obtainKrakenToken']['token']
    except (KeyError, TypeError):
        raise ValueError('Unable to retrieve Octopus GraphQL metadata') from None
    if not isinstance(token, str) or not token:
        raise ValueError('Unable to retrieve Octopus GraphQL metadata')
    return token

def gas_consumption_unit(serial_number):
    token = graphql_token()
    account_data = graphql_request(
        'query GasConsumptionUnits($accountNumber: String!) '
        '{ account(accountNumber: $accountNumber) '
        '{ properties { gasMeterPoints { meters { serialNumber consumptionUnits } } } } }',
        {'accountNumber': ACCOUNT},
        token,
    )
    try:
        meters = [meter for prop in account_data['account']['properties']
                  for point in prop['gasMeterPoints'] for meter in point['meters']]
    except (KeyError, TypeError):
        raise ValueError('Unable to retrieve Octopus GraphQL metadata') from None
    return next((meter.get('consumptionUnits') for meter in meters
                 if meter.get('serialNumber') == serial_number), None)

def parse_api_datetime(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Invalid agreement timestamp in Octopus account response') from None
    if parsed.tzinfo is None:
        raise ValueError('Invalid agreement timestamp in Octopus account response')
    return parsed

def agreement_is_active(agreement, as_of):
    valid_from = parse_api_datetime(agreement.get('valid_from'))
    valid_to = parse_api_datetime(agreement.get('valid_to'))
    return (valid_from is None or valid_from <= as_of) and (valid_to is None or as_of < valid_to)

def agreement_overlaps(agreement, window_start, window_end):
    valid_from = parse_api_datetime(agreement.get('valid_from'))
    valid_to = parse_api_datetime(agreement.get('valid_to'))
    return (valid_from is None or valid_from < window_end) and (valid_to is None or window_start < valid_to)

def consumption_measurement(fuel, serial_number=None):
    if fuel == 'electricity':
        return {
            'value_field': 'consumption',
            'quantity': 'energy',
            'unit': 'kWh',
            'unit_status': 'known',
            'conversion_applied': False,
        }
    try:
        unit = gas_consumption_unit(serial_number)
        unit = unit.strip() if isinstance(unit, str) else unit
        unit_status = 'known' if unit else 'unavailable_for_meter'
    except ValueError:
        unit = None
        unit_status = 'lookup_failed'
    normalized = unit.strip().lower().replace(' ', '') if isinstance(unit, str) else None
    if normalized == 'kwh':
        unit, quantity = 'kWh', 'energy'
    elif normalized in ('m3', 'm^3', 'm³'):
        unit, quantity = 'm³', 'volume'
    else:
        quantity = 'volume_or_energy'
    return {
        'value_field': 'consumption',
        'quantity': quantity,
        'unit': unit,
        'unit_status': unit_status,
        'unit_source': 'kraken_graphql_consumptionUnits' if unit else None,
        'conversion_applied': False,
    }

def meter_inventory(account_data, as_of=None):
    """Return compatible flat meters plus supply-point selection metadata."""
    as_of = datetime.now(timezone.utc) if as_of is None else as_of
    meters = []
    supply_points = []
    for prop in account_data.get('properties', []):
        for fuel, key, identifier in [('electricity', 'electricity_meter_points', 'mpan'), ('gas', 'gas_meter_points', 'mprn')]:
            for point in prop.get(key, []):
                is_export = bool(point.get('is_export', False))
                direction = 'export' if is_export else ('import' if fuel == 'electricity' else 'consumption')
                agreements = point.get('agreements', [])
                active_agreements = [agreement for agreement in agreements if agreement_is_active(agreement, as_of)]
                candidates = [meter.get('serial_number') for meter in point.get('meters', []) if meter.get('serial_number')]
                if len(candidates) == 1:
                    meter_selection_status = 'unambiguous'
                elif candidates:
                    meter_selection_status = 'ambiguous'
                else:
                    meter_selection_status = 'unavailable'
                if len(active_agreements) == 1:
                    agreement_selection_status = 'unambiguous'
                elif active_agreements:
                    agreement_selection_status = 'ambiguous'
                else:
                    agreement_selection_status = 'unavailable'
                meter_point = str(point.get(identifier, ''))
                supply_points.append({
                    'fuel': fuel,
                    'direction': direction,
                    'meter_point': meter_point,
                    'meter_candidates': candidates,
                    'meter_selection_status': meter_selection_status,
                    'meter_validity_known': False,
                    'agreements': agreements,
                    'active_agreements': active_agreements,
                    'agreement_selection_status': agreement_selection_status,
                })
                for serial_number in candidates:
                    meters.append({
                        'fuel': fuel,
                        'meter_point': meter_point,
                        'serial_number': serial_number,
                        'agreements': agreements,
                        'is_export': is_export,
                        'direction': direction,
                        'meter_selection_status': meter_selection_status,
                        'active_agreements': active_agreements,
                    })
    return {'meters': meters, 'supply_points': supply_points, 'as_of': as_of.isoformat()}

def supplies(rest):
    return meter_inventory(account(rest))['meters']

@mcp.tool()
def list_meters() -> dict:
    """List account meters and known tariff agreements; identifies import/export where available."""
    with OctopusREST() as rest:
        inventory = meter_inventory(account(rest))
    inventory['note'] = ('A supply point with multiple meter candidates is ambiguous because the account API does not provide '
                         'physical meter validity dates. Do not infer the current meter from the active tariff agreement.')
    return inventory

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

def consumption_coverage(records, window_start, window_end):
    """Describe half-hour coverage for a UTC window without treating gaps as zero."""
    interval = timedelta(minutes=30)
    expected = set()
    cursor = window_start
    while cursor < window_end:
        expected.add((cursor, cursor + interval))
        cursor += interval

    observed = set()
    for record in records:
        start = datetime.fromisoformat(record['interval_start'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(record['interval_end'].replace('Z', '+00:00'))
        if end - start != interval or (start - window_start) % interval:
            raise ValueError('Unexpected consumption interval; expected aligned half-hour readings')
        observed.add((start, end))

    missing = sorted(expected - observed)
    gaps = []
    for start, end in missing:
        if gaps and datetime.fromisoformat(gaps[-1]['interval_end'].replace('Z', '+00:00')) == start:
            gaps[-1]['interval_end'] = end.isoformat()
            gaps[-1]['missing_interval_count'] += 1
        else:
            gaps.append({
                'interval_start': start.isoformat(),
                'interval_end': end.isoformat(),
                'missing_interval_count': 1,
            })
    return {
        'interval_minutes': 30,
        'expected_interval_count': len(expected),
        'returned_interval_count': len(observed),
        'missing_interval_count': len(missing),
        'complete': not missing,
        'gaps': gaps,
    }

@mcp.tool()
def consumption(fuel: str, meter_point: str, serial_number: str, start_date: str, end_date: str) -> dict:
    """Get meter consumption for inclusive UK dates YYYY-MM-DD, up to 31 days. Use list_meters first. Data can be delayed or missing; gas units may be m3."""
    if fuel not in ('electricity', 'gas'):
        raise ValueError('fuel must be electricity or gas')
    window_start, window_end = uk_date_window(start_date, end_date)
    path = f'{fuel}-meter-points/{quote(meter_point, safe="")}/meters/{quote(serial_number, safe="")}/consumption/'
    # The API default ordering paginates reliably in the observed live case;
    # order_by=period returned overlapping pages and omitted intervals.
    params = {'period_from': window_start.isoformat(), 'period_to': window_end.isoformat(), 'page_size': 250}
    with OctopusREST() as rest:
        supply = next((s for s in supplies(rest) if s['fuel'] == fuel and s['meter_point'] == meter_point
                       and s['serial_number'] == serial_number), None)
        if supply is None:
            raise ValueError('Meter does not belong to the configured account')
        records = paginated_results(rest, path, params)
    # Octopus can return a reading starting at the exclusive period_to boundary.
    # Filter it out, while preserving legitimate short/long DST days.
    records = filter_consumption_records(records, window_start, window_end)
    coverage = consumption_coverage(records, window_start, window_end)
    applicable_agreements = [agreement for agreement in supply.get('agreements', [])
                             if agreement_overlaps(agreement, window_start, window_end)]
    measurement = consumption_measurement(fuel, serial_number)
    if fuel == 'electricity':
        unit_note = 'Consumption values are kWh.'
    elif measurement['unit']:
        unit_note = f"Gas consumption values are reported by Octopus in {measurement['unit']}. No conversion has been applied."
    else:
        unit_note = 'The gas unit could not be established for this meter. No conversion has been applied.'
    return {'fuel': fuel, 'start_date': start_date, 'end_date_inclusive': end_date, 'records': records, 'record_count': len(records), 'coverage': coverage, 'measurement': measurement, 'applicable_agreements': applicable_agreements, 'unit_note': unit_note, 'coverage_note': 'Missing or delayed intervals are not zero; dates converted from Europe/London. Returned intervals are sorted and restricted to the requested date window.'}

@mcp.tool()
def tariff_rates(product_code: str, tariff_code: str, fuel: str, start_date: str, end_date: str) -> dict:
    """Fetch published standard unit rates, standing charges and sources for a tariff, up to 31 inclusive UK dates."""
    if fuel not in ('electricity', 'gas'):
        raise ValueError('fuel must be electricity or gas')
    period = tariff_rate_period(start_date, end_date)
    base = tariff_path(product_code, tariff_code, fuel)
    paths = {kind: base + kind + '/' for kind in ('standard-unit-rates', 'standing-charges')}
    return {
        'product_code': product_code,
        'tariff_code': tariff_code,
        'fuel': fuel,
        'start_date': start_date,
        'end_date_inclusive': end_date,
        **published_rate_data(paths, period),
        'note': ('For export estimates, use the export supply agreement and match each reading to a published rate '
                 'that covers its interval. Dual-register pricing, EV dispatch and discounts may require other data.'),
    }

@mcp.tool()
def tariff_products(available_at: str) -> dict:
    """List Octopus products available at an aware ISO timestamp. Availability is not household eligibility."""
    try:
        instant = datetime.fromisoformat(available_at.replace('Z', '+00:00'))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('available_at must be an ISO timestamp with a timezone') from None
    available_at_utc = instant.astimezone(timezone.utc).isoformat()
    with OctopusREST() as rest:
        products = paginated_results(rest, 'products/', {'available_at': available_at_utc, 'page_size': 100})
    return {'available_at': available_at_utc, 'products': products,
            'eligibility': 'unknown', 'note': 'Published availability does not establish household eligibility. Check region, meter, payment method, export and product-specific requirements.'}

@mcp.tool()
def tariff_product(product_code: str) -> dict:
    """Retrieve a product and its regional tariff variants; eligibility is not established."""
    if not isinstance(product_code, str) or not TARIFF_IDENTIFIER.fullmatch(product_code):
        raise ValueError('Invalid product code')
    with OctopusREST() as rest:
        product = rest.get(f'products/{product_code}/')
    if not isinstance(product, dict):
        raise ValueError('Invalid product response')
    return {'product': product, 'eligibility': 'unknown',
            'note': 'Regional variants and published prices do not establish household eligibility or an actual bill.'}

def tariff_path(product_code, tariff_code, fuel):
    return f'products/{quote(product_code, safe="")}/{fuel}-tariffs/{quote(tariff_code, safe="")}/'

def electricity_tariff_path(product_code, tariff_code):
    for code in (product_code, tariff_code):
        if not isinstance(code, str) or not TARIFF_IDENTIFIER.fullmatch(code):
            raise ValueError('Invalid product or tariff code')
    return tariff_path(product_code, tariff_code, 'electricity')

def uk_date_window(start_date, end_date):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 30:
        raise ValueError('Use at most 31 inclusive days')
    return (
        datetime.combine(start, datetime.min.time(), UK_TIMEZONE).astimezone(timezone.utc),
        datetime.combine(end + timedelta(days=1), datetime.min.time(), UK_TIMEZONE).astimezone(timezone.utc),
    )

def tariff_rate_period(start_date, end_date):
    start, end = uk_date_window(start_date, end_date)
    return {'period_from': start.isoformat(), 'period_to': end.isoformat()}

def fetch_tariff_rates(paths, period):
    with OctopusREST() as rest:
        params = {**period, 'page_size': 250}
        return {kind: paginated_results(rest, path, params) for kind, path in paths.items()}

def published_rate_data(paths, period):
    rates = fetch_tariff_rates(paths, period)
    return {
        'requested_period_utc': period,
        'sources': {kind: API + path for kind, path in paths.items()},
        'rates': rates,
        'units': {'unit_rates': 'pence/kWh', 'standing_charges': 'pence/day'},
        'empty_rate_categories': [kind for kind, rows in rates.items() if not rows],
    }

@mcp.tool()
def tariff_dual_rates(product_code: str, tariff_code: str, fuel: str, start_date: str, end_date: str) -> dict:
    """Fetch published day and night unit rates for a dual-register tariff, for up to 31 UK dates."""
    base = electricity_tariff_path(product_code, tariff_code)
    if fuel != 'electricity':
        raise ValueError('Dual-register rates are supported for electricity only')
    period = tariff_rate_period(start_date, end_date)
    kinds = ('day-unit-rates', 'night-unit-rates', 'standing-charges')
    rates = fetch_tariff_rates({kind: base + kind + '/' for kind in kinds}, period)
    return {'rates': rates, 'note': 'Rates are pence; use VAT-inclusive values. Day/night switching times and meter register allocation must be verified separately. These rates are not a bill or a cost comparison.'}

@mcp.tool()
def tariff_ev_rates(product_code: str, tariff_code: str, start_date: str, end_date: str) -> dict:
    """Fetch published rates for a four-rate EV electricity tariff for up to 31 inclusive UK dates.

    Use tariff_product to find codes under four_rate_ev_electricity_tariffs.
    Returns day, night, EV device peak and off-peak, and standing-charge records.
    """
    base = electricity_tariff_path(product_code, tariff_code)
    period = tariff_rate_period(start_date, end_date)
    kinds = ('day-unit-rates', 'night-unit-rates', 'ev-device-peak-unit-rates',
             'ev-device-off-peak-unit-rates', 'standing-charges')
    paths = {kind: base + kind + '/' for kind in kinds}
    return {
        'product_code': product_code,
        'tariff_code': tariff_code,
        'start_date': start_date,
        'end_date_inclusive': end_date,
        **published_rate_data(paths, period),
        'note': ('Rate records preserve Octopus VAT values, payment method and validity timestamps. '
                 'Validity timestamps are for the published price, not the daily switching hours. '
                 'Account-specific EV dispatches and rate applicability require separate data.'),
    }

BILLING_AGREEMENTS = """
query BillingAgreements($account: String!, $start: DateTime!) {
  account(accountNumber: $account) {
    properties(activeFrom: $start) {
      electricityMeterPoints {
        mpan direction agreements(includeInactive: true, validAfter: $start) {
          id valid_from: validFrom valid_to: validTo
        }
      }
    }
  }
}
"""

BILLING_ITEMS = """
query BillingItems($id: ID!, $start: DateTime!, $after: String) {
  electricityAgreement(id: $id) {
    ... on ElectricityAgreementType {
      lineItems(startAt: $start, grouping: HALF_HOUR, itemType: CONSUMPTION_CHARGE,
                timezone: "Europe/London", first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges { node { startAt endAt netAmount numberOfUnits settlementUnit itemType } }
      }
    }
  }
}
"""


@mcp.tool()
def billing(meter_point: str, day: str, agreement_id: str | None = None,
            after: str | None = None) -> dict:
    """Get Kraken consumption charge lines for an account electricity import point and UK date.
    Use list_meters for the meter point. For another page pass the same inputs, agreement_id
    and returned next_cursor as after. Amounts are upstream net values, without a verified
    currency scale or statement reconciliation. Rows can span more than a half hour.
    """
    start, end = uk_date_window(day, day)
    if not meter_point.strip() or (after is not None and (not after or not agreement_id)):
        raise ValueError('Provide a meter point and pair any page cursor with its agreement ID.')
    token = graphql_token()
    inventory = graphql_request(BILLING_AGREEMENTS, {'account': ACCOUNT, 'start': start.isoformat()}, token)
    try:
        candidates = {
            str(agreement['id'])
            for prop in inventory['account']['properties']
            for point in prop['electricityMeterPoints']
            if point['mpan'] == meter_point and point['direction'] == 'IMPORT'
            for agreement in point['agreements']
            if agreement['id'] is not None and agreement_overlaps(agreement, start, end)
        }
    except (KeyError, TypeError, AttributeError):
        raise ValueError('Kraken returned incomplete billing agreement data.') from None
    if not candidates or (agreement_id is not None and agreement_id not in candidates):
        raise ValueError('No matching import agreement for this account, point and day.')
    if agreement_id is None and len(candidates) > 1:
        return {'status': 'select_agreement', 'agreement_ids': sorted(candidates)}
    selected = agreement_id or next(iter(candidates))
    data = graphql_request(BILLING_ITEMS, {'id': selected, 'start': start.isoformat(), 'after': after}, token)
    records = []
    try:
        page = data['electricityAgreement']['lineItems']
        info = page['pageInfo']
        more = info['hasNextPage']
        cursor = info['endCursor'] if more else None
        if (not isinstance(more, bool) or not isinstance(page['edges'], list)
                or (more and (not isinstance(cursor, str) or not cursor or cursor == after))):
            raise ValueError
        for edge in page['edges']:
            row = edge['node']
            left = parse_api_datetime(row['startAt'])
            right = parse_api_datetime(row['endAt'])
            if left is None or right is None or right <= left:
                raise ValueError
            if left < end and right > start:
                records.append({key: row[key] for key in (
                    'startAt', 'endAt', 'netAmount', 'numberOfUnits', 'settlementUnit', 'itemType')})
    except (KeyError, TypeError, ValueError):
        raise ValueError('Kraken returned incomplete billing line item data.') from None
    return {'status': 'ok', 'source': 'Kraken electricityAgreement.lineItems', 'day': day,
            'agreement_id': selected, 'records': records, 'next_cursor': cursor,
            'amount_basis': 'Upstream netAmount; currency scale and final billed rate unverified.'}


if __name__ == '__main__':
    mcp.run(transport='streamable-http')
