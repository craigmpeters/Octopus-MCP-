import asyncio
import json

import httpx
import pytest

import server
import upstream

pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_api(monkeypatch):
    """Keep the real HTTPX client, URL parsing and auth flow around a mock transport."""
    monkeypatch.setattr(server, 'KEY', 'test-key')
    monkeypatch.setattr(server, 'ACCOUNT', 'test-account')
    client_type = httpx.AsyncClient

    def install(handler):
        clients = []

        def client(**kwargs):
            instance = client_type(transport=httpx.MockTransport(handler), **kwargs)
            clients.append(instance)
            return instance

        monkeypatch.setattr(upstream.httpx, 'AsyncClient', client)
        return clients

    return install


def json_response(data):
    return httpx.Response(200, stream=httpx.ByteStream(json.dumps(data).encode()))


@pytest.mark.parametrize('continuation', [
    upstream.GRAPHQL_API, '//other.invalid/page', 'http://api.octopus.energy/page',
    'https://api.octopus.energy:444/page', 'https://user@api.octopus.energy/page',
])
async def test_foreign_continuation_rejected_before_second_request(mock_api, continuation):
    requests = []

    def handler(request):
        requests.append(request)
        return json_response({'results': [], 'next': continuation})

    clients = mock_api(handler)
    with pytest.raises(ValueError, match='pagination origin'):
        await server.tariff_products('2025-01-01T00:00:00Z')
    assert len(requests) == 1
    assert requests[0].url.host == 'api.octopus.energy'
    assert requests[0].headers['Authorization'].startswith('Basic ')
    assert clients[0].is_closed


async def test_same_origin_continuation_shares_client(mock_api):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return json_response({'results': [1], 'next': '?page=2'})
        return json_response({'results': [2]})

    clients = mock_api(handler)
    result = await server.tariff_products('2025-01-01T00:00:00Z')
    assert result['products'] == [1, 2]
    assert str(requests[1].url) == upstream.API + 'products/?page=2'
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.parametrize('tool', ['consumption', 'tariff_rates'])
@pytest.mark.parametrize('page', [{}, {'results': None}, [], {'results': []}])
async def test_invalid_pages_and_empty_results(mock_api, page, tool):
    def handler(request):
        if '/accounts/' in request.url.path:
            return json_response({'properties': [{'electricity_meter_points': [
                {'mpan': 'point', 'meters': [{'serial_number': 'serial'}]}]}]})
        return json_response(page)

    mock_api(handler)
    if tool == 'consumption':
        call = server.consumption('electricity', 'point', 'serial', '2025-01-01', '2025-01-01')
    else:
        call = server.tariff_rates('product', 'tariff', 'gas', '2025-01-01', '2025-01-01')
    if page != {'results': []}:
        with pytest.raises(ValueError, match='Invalid results list'):
            await call
    elif tool == 'consumption':
        assert (await call)['coverage']['missing_interval_count'] == 48
    else:
        assert (await call)['rates'] == {'standard-unit-rates': [], 'standing-charges': []}


async def test_invalid_json_is_redacted(mock_api):
    mock_api(lambda request: httpx.Response(200, stream=httpx.ByteStream(b'sensitive-body')))
    with pytest.raises(ValueError, match='^Invalid JSON in Octopus response$'):
        await server.tariff_product('TEST')


async def test_ev_categories_share_byte_budget(mock_api, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return json_response({'results': []})

    clients = mock_api(handler)
    monkeypatch.setattr(upstream, 'MAX_CALL_BYTES', len(json.dumps({'results': []})) + 1)
    with pytest.raises(ValueError, match='size limit'):
        await server.tariff_ev_rates('TEST', 'EV', '2025-01-01', '2025-01-01')
    assert len(requests) == 2
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.parametrize('stall', [False, True], ids=['oversized', 'stalled'])
async def test_stream_aborted_and_closed(mock_api, monkeypatch, stall):
    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'1234'
            if stall:
                await asyncio.Event().wait()
            yield b'5'
            pytest.fail('Read past the byte limit')

        async def aclose(self):
            self.closed = True

    stream = Stream()
    clients = mock_api(lambda request: httpx.Response(200, stream=stream))
    monkeypatch.setattr(upstream, 'MAX_RESPONSE_BYTES', 4)
    monkeypatch.setattr(upstream, 'CALL_TIMEOUT_SECONDS', 0.1 if stall else 60)
    with pytest.raises(ValueError, match='deadline' if stall else 'size limit'):
        await server.tariff_product('TEST')
    assert stream.closed
    assert clients[0].is_closed


async def test_graphql_uses_only_its_own_auth(mock_api):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == 'GET':
            if '/accounts/' in request.url.path:
                return json_response({'properties': [{'gas_meter_points': [
                    {'mprn': 'point', 'meters': [{'serial_number': 'serial'}]}]}]})
            return json_response({'results': []})
        if len(requests) == 3:
            return json_response({'data': {'obtainKrakenToken': {'token': 'test-token'}}})
        return json_response({'data': {'account': {'properties': []}}})

    clients = mock_api(handler)
    result = await server.consumption('gas', 'point', 'serial', '2025-01-01', '2025-01-01')
    assert result['measurement']['unit_status'] == 'unavailable_for_meter'
    assert len(requests) == 4
    assert all(str(req.url) == upstream.GRAPHQL_API for req in requests[2:])
    assert 'Authorization' not in requests[2].headers
    assert requests[3].headers['Authorization'] == 'test-token'
    assert len(clients) == 1 and clients[0].is_closed


async def test_mcp_dispatch_preserves_tariff_product_result(mock_api):
    mock_api(lambda request: json_response({'code': 'TEST'}))
    names = {tool.name for tool in await server.mcp.list_tools()}
    assert names == {'list_meters', 'consumption', 'tariff_products', 'tariff_product',
                     'tariff_rates', 'tariff_dual_rates', 'tariff_ev_rates'}
    content = await server.mcp.call_tool('tariff_product', {'product_code': 'TEST'})
    result = json.loads(content[0].text)
    assert result['product'] == {'code': 'TEST'}
    assert result['eligibility'] == 'unknown'


async def test_encoded_body_is_rejected_before_reading(mock_api):
    class UnexpectedBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail('An encoded response must be rejected before decoding')
            yield b''

    clients = mock_api(lambda request: httpx.Response(
        200, headers={'Content-Encoding': 'gzip'}, stream=UnexpectedBody()))
    with pytest.raises(ValueError, match='response encoding'):
        await server.tariff_product('TEST')
    assert clients[0].is_closed
