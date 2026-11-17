from datetime import datetime, timezone
from unittest.mock import patch

import server


ACCOUNT = {
    'properties': [{
        'electricity_meter_points': [
            {
                'mpan': 'import-point',
                'is_export': False,
                'meters': [{'serial_number': 'old-meter'}, {'serial_number': 'new-meter'}],
                'agreements': [
                    {'tariff_code': 'OLD', 'valid_from': '2024-01-01T00:00:00Z', 'valid_to': '2025-01-01T00:00:00Z'},
                    {'tariff_code': 'CURRENT', 'valid_from': '2025-01-01T00:00:00Z', 'valid_to': None},
                ],
            },
            {
                'mpan': 'export-point',
                'is_export': True,
                'meters': [{'serial_number': 'export-meter'}],
                'agreements': [],
            },
        ],
        'gas_meter_points': [{
            'mprn': 'gas-point',
            'meters': [{'serial_number': 'gas-meter'}],
            'agreements': [{'tariff_code': 'GAS', 'valid_from': '2025-01-01T00:00:00Z', 'valid_to': None}],
        }],
    }],
}
AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_inventory_separates_directions_and_flags_ambiguous_meters():
    inventory = server.meter_inventory(ACCOUNT, AS_OF)
    points = inventory['supply_points']
    assert [(point['fuel'], point['direction']) for point in points] == [
        ('electricity', 'import'), ('electricity', 'export'), ('gas', 'consumption')]
    assert points[0]['meter_candidates'] == ['old-meter', 'new-meter']
    assert points[0]['meter_selection_status'] == 'ambiguous'
    assert points[0]['meter_validity_known'] is False
    assert [agreement['tariff_code'] for agreement in points[0]['active_agreements']] == ['CURRENT']
    assert points[0]['agreement_selection_status'] == 'unambiguous'
    assert points[1]['meter_selection_status'] == 'unambiguous'
    assert points[1]['agreement_selection_status'] == 'unavailable'


def test_flat_meter_list_remains_compatible_and_adds_selection_metadata():
    inventory = server.meter_inventory(ACCOUNT, AS_OF)
    old_meter = inventory['meters'][0]
    assert old_meter['meter_point'] == 'import-point'
    assert old_meter['serial_number'] == 'old-meter'
    assert old_meter['is_export'] is False
    assert old_meter['direction'] == 'import'
    assert old_meter['meter_selection_status'] == 'ambiguous'
    assert [agreement['tariff_code'] for agreement in old_meter['active_agreements']] == ['CURRENT']


def test_list_meters_reports_that_active_agreement_does_not_select_meter():
    with patch.object(server, 'account', return_value=ACCOUNT), patch.object(server, 'datetime', wraps=datetime) as mocked_datetime:
        mocked_datetime.now.return_value = AS_OF
        result = server.list_meters()
    assert result['supply_points'][0]['meter_selection_status'] == 'ambiguous'
    assert 'Do not infer the current meter' in result['note']


def test_overlapping_active_agreements_are_reported_as_ambiguous():
    account = {'properties': [{'electricity_meter_points': [{
        'mpan': 'point',
        'meters': [{'serial_number': 'meter'}],
        'agreements': [
            {'tariff_code': 'ONE', 'valid_from': '2025-01-01T00:00:00Z', 'valid_to': None},
            {'tariff_code': 'TWO', 'valid_from': '2025-06-01T00:00:00Z', 'valid_to': None},
        ],
    }]}]}
    point = server.meter_inventory(account, AS_OF)['supply_points'][0]
    assert point['agreement_selection_status'] == 'ambiguous'
    assert len(point['active_agreements']) == 2
