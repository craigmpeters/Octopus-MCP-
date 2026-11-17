import pytest
import server


def test_catalogue_paginates_and_marks_eligibility_unknown(monkeypatch):
    calls = []
    def fake_get(path, params=None):
        calls.append((path, params))
        if len(calls) == 1:
            return {'results': [{'code': 'FIRST'}], 'next': 'https://api.octopus.energy/v1/products/?page=2'}
        return {'results': [{'code': 'SECOND'}], 'next': None}
    monkeypatch.setattr(server, 'get', fake_get)
    result = server.tariff_products('2025-03-30T01:00:00+01:00')
    assert result['available_at'] == '2025-03-30T00:00:00+00:00'
    assert [p['code'] for p in result['products']] == ['FIRST', 'SECOND']
    assert result['eligibility'] == 'unknown'
    assert calls[1][1] is None


def test_catalogue_rejects_naive_time_and_repeated_page(monkeypatch):
    with pytest.raises(ValueError, match='timezone'):
        server.tariff_products('2025-01-01T00:00:00')
    monkeypatch.setattr(server, 'get', lambda *args: {'results': [], 'next': 'https://api.octopus.energy/v1/products/?page=2'})
    with pytest.raises(ValueError, match='pagination'):
        server.tariff_products('2025-01-01T00:00:00Z')


def test_product_details_preserve_variants_and_reject_path_injection(monkeypatch):
    monkeypatch.setattr(server, 'get', lambda path: {'code': 'TEST-1', 'single_register_electricity_tariffs': {'_A': {'direct_debit_monthly': {'code': 'E-1R-TEST-1-A'}}}})
    result = server.tariff_product('TEST-1')
    assert result['product']['single_register_electricity_tariffs']['_A']['direct_debit_monthly']['code'] == 'E-1R-TEST-1-A'
    assert result['eligibility'] == 'unknown'
    for code in ('../accounts', 'a/b', '.', ''):
        with pytest.raises(ValueError, match='Invalid product code'):
            server.tariff_product(code)


def test_dual_rates_fetches_each_register_with_london_date_boundaries(monkeypatch):
    calls = []
    def fake_get(path, params=None):
        calls.append((path, params))
        return {'results': [{'value_inc_vat': 12}], 'next': None}
    monkeypatch.setattr(server, 'get', fake_get)
    result = server.tariff_dual_rates('TEST', 'E-2R-TEST-A', 'electricity', '2025-03-30', '2025-03-30')
    assert set(result['rates']) == {'day-unit-rates', 'night-unit-rates', 'standing-charges'}
    assert calls[0][1]['period_from'] == '2025-03-30T00:00:00+00:00'
    assert calls[0][1]['period_to'] == '2025-03-30T23:00:00+00:00'
    with pytest.raises(ValueError):
        server.tariff_dual_rates('../bad', 'E-2R-TEST-A', 'electricity', '2025-03-30', '2025-03-30')
