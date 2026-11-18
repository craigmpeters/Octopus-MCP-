import httpx
import pytest

import server


DAY = '2025-01-01'
NEXT_PAGE = server.API + 'collection/?page=2'


@pytest.fixture
def mock_rest(monkeypatch):
    def install(*responses):
        requests = []
        pages = iter(responses)

        def respond(request):
            requests.append(request)
            page = next(pages)
            if isinstance(page, bytes):
                return httpx.Response(200, content=page)
            return httpx.Response(200, json=page)

        client = httpx.Client
        transport = httpx.MockTransport(respond)
        monkeypatch.setattr(server.httpx, 'Client', lambda **kwargs: client(transport=transport, **kwargs))
        monkeypatch.setattr(server, 'KEY', 'synthetic')
        monkeypatch.setattr(server, 'ACCOUNT', 'synthetic')
        return requests

    return install


@pytest.fixture
def fetch_consumption(monkeypatch):
    supply = {'fuel': 'electricity', 'meter_point': '123', 'serial_number': 'test-meter'}
    monkeypatch.setattr(server, 'supplies', lambda: [supply])
    return lambda: server.consumption('electricity', '123', 'test-meter', DAY, DAY)


def fetch_standard_rates():
    return server.tariff_rates('TEST', 'E-1R-TEST-A', 'electricity', DAY, DAY)


@pytest.mark.parametrize('tool', ['fetch_consumption', 'fetch_standard_rates'])
@pytest.mark.parametrize(('page', 'message'), [
    ([], 'Octopus API page is missing a valid results list'),
    ({}, 'Octopus API page is missing a valid results list'),
    ({'results': {}}, 'Octopus API page is missing a valid results list'),
    ({'results': [], 'next': False}, 'Invalid Octopus API pagination continuation'),
    ({'results': [], 'next': ' '}, 'Invalid Octopus API pagination continuation'),
    (b'{"test-meter":', 'Octopus API returned invalid JSON'),
])
def test_malformed_second_page_fails_tool(mock_rest, fetch_consumption, tool, page, message):
    fetch = fetch_consumption if tool == 'fetch_consumption' else fetch_standard_rates
    requests = mock_rest({'results': [], 'next': NEXT_PAGE}, page)

    with pytest.raises(ValueError) as error:
        fetch()

    assert str(error.value) == message
    assert len(requests) == 2


@pytest.mark.parametrize('tool', ['fetch_consumption', 'fetch_standard_rates'])
def test_repeated_continuation_stops_before_third_request(mock_rest, fetch_consumption, tool):
    fetch = fetch_consumption if tool == 'fetch_consumption' else fetch_standard_rates
    page = {'results': [], 'next': NEXT_PAGE}
    requests = mock_rest(page, page)

    with pytest.raises(ValueError, match='^Invalid Octopus API pagination continuation$'):
        fetch()

    assert len(requests) == 2


def test_empty_consumption_page_reports_missing_intervals(mock_rest, fetch_consumption):
    mock_rest({'results': []})

    result = fetch_consumption()

    assert result['records'] == []
    assert result['coverage']['missing_interval_count'] == 48
    assert result['coverage']['complete'] is False


def test_standard_rates_collect_pages_and_preserve_empty_categories(mock_rest):
    first = {'value_inc_vat': 7}
    second = {'value_inc_vat': 8}
    requests = mock_rest(
        {'results': [first], 'next': NEXT_PAGE},
        {'results': [second], 'next': None},
        {'results': [], 'next': None},
    )

    result = fetch_standard_rates()

    assert result['rates'] == {'standard-unit-rates': [first, second], 'standing-charges': []}
    assert requests[0].url.params['page_size'] == '250'
    assert str(requests[1].url) == NEXT_PAGE
    assert requests[2].url.path.endswith('/standing-charges/')
