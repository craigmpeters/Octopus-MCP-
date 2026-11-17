import pytest
from unittest.mock import AsyncMock

import server
from upstream import Upstream

pytestmark = pytest.mark.anyio


async def test_catalogue_paginates_and_marks_eligibility_unknown(monkeypatch):
    calls = []
    async def fake_get(self, path, params=None):
        calls.append((path, params))
        if len(calls) == 1:
            return {'results': [{'code': 'FIRST'}], 'next': 'https://api.octopus.energy/v1/products/?page=2'}
        return {'results': [{'code': 'SECOND'}], 'next': None}
    monkeypatch.setattr(Upstream, 'get', fake_get)
    result = await server.tariff_products('2025-03-30T01:00:00+01:00')
    assert result['available_at'] == '2025-03-30T00:00:00+00:00'
    assert [p['code'] for p in result['products']] == ['FIRST', 'SECOND']
    assert result['eligibility'] == 'unknown'
    assert calls[1][1] is None


async def test_catalogue_rejects_naive_time_and_repeated_page(monkeypatch):
    with pytest.raises(ValueError, match='timezone'):
        await server.tariff_products('2025-01-01T00:00:00')
    monkeypatch.setattr(Upstream, 'get', AsyncMock(return_value={'results': [], 'next': 'https://api.octopus.energy/v1/products/?page=2'}))
    with pytest.raises(ValueError, match='pagination'):
        await server.tariff_products('2025-01-01T00:00:00Z')


async def test_product_details_preserve_variants_and_reject_path_injection(monkeypatch):
    monkeypatch.setattr(Upstream, 'get', AsyncMock(return_value={'code': 'TEST-1', 'single_register_electricity_tariffs': {'_A': {'direct_debit_monthly': {'code': 'E-1R-TEST-1-A'}}}}))
    result = await server.tariff_product('TEST-1')
    assert result['product']['single_register_electricity_tariffs']['_A']['direct_debit_monthly']['code'] == 'E-1R-TEST-1-A'
    assert result['eligibility'] == 'unknown'
    for code in ('../accounts', 'a/b', '.', ''):
        with pytest.raises(ValueError, match='Invalid product code'):
            await server.tariff_product(code)


async def test_dual_rates_fetches_each_register_with_london_date_boundaries(monkeypatch):
    calls = []
    async def fake_get(self, path, params=None):
        calls.append((path, params))
        return {'results': [{'value_inc_vat': 12}], 'next': None}
    monkeypatch.setattr(Upstream, 'get', fake_get)
    result = await server.tariff_dual_rates('TEST', 'E-2R-TEST-A', 'electricity', '2025-03-30', '2025-03-30')
    assert set(result['rates']) == {'day-unit-rates', 'night-unit-rates', 'standing-charges'}
    assert calls[0][1]['period_from'] == '2025-03-30T00:00:00+00:00'
    assert calls[0][1]['period_to'] == '2025-03-30T23:00:00+00:00'
    with pytest.raises(ValueError):
        await server.tariff_dual_rates('../bad', 'E-2R-TEST-A', 'electricity', '2025-03-30', '2025-03-30')


async def test_ev_rates_keep_published_bands_separate_and_report_empty_category(monkeypatch):
    base = 'products/EV-TEST/electricity-tariffs/E-1R-EV-TEST-A/'
    second_page = server.API + base + 'ev-device-off-peak-unit-rates/?page=2'
    row = {
        'value_exc_vat': 6.667, 'value_inc_vat': 7.00035,
        'valid_from': '2025-09-01T00:00:00Z', 'valid_to': None,
        'payment_method': 'DIRECT_DEBIT',
    }
    later = {**row, 'value_inc_vat': 7.5, 'payment_method': 'NON_DIRECT_DEBIT'}
    calls = []

    async def fake_get(self, path, params=None):
        calls.append((path, params))
        if path == second_page:
            return {'results': [later], 'next': None}
        if path == base + 'ev-device-peak-unit-rates/':
            return {'results': [], 'next': None}
        next_page = second_page if path == base + 'ev-device-off-peak-unit-rates/' else None
        return {'results': [row], 'next': next_page}

    monkeypatch.setattr(Upstream, 'get', fake_get)

    result = await server.tariff_ev_rates('EV-TEST', 'E-1R-EV-TEST-A', '2025-10-26', '2025-10-26')

    assert result['requested_period_utc'] == {
        'period_from': '2025-10-25T23:00:00+00:00', 'period_to': '2025-10-27T00:00:00+00:00',
    }
    assert (second_page, None) in calls
    assert result['rates'] == {
        'day-unit-rates': [row], 'night-unit-rates': [row],
        'ev-device-peak-unit-rates': [], 'ev-device-off-peak-unit-rates': [row, later],
        'standing-charges': [row],
    }
    assert result['empty_rate_categories'] == ['ev-device-peak-unit-rates']
    assert result['sources']['ev-device-off-peak-unit-rates'] == second_page.removesuffix('?page=2')
    assert result['units'] == {'unit_rates': 'pence/kWh', 'standing_charges': 'pence/day'}


async def test_ev_rates_rejects_invalid_request_before_fetching(monkeypatch):
    async def unexpected_get(*args):
        pytest.fail('Invalid input must be rejected before fetching')

    monkeypatch.setattr(Upstream, 'get', unexpected_get)
    with pytest.raises(ValueError, match='Invalid product or tariff code'):
        await server.tariff_ev_rates('EV-TEST', 'bad/code', '2025-01-01', '2025-01-02')
    with pytest.raises(ValueError, match='31 inclusive days'):
        await server.tariff_ev_rates('EV-TEST', 'E-1R-EV-TEST-A', '2025-01-01', '2025-02-01')
