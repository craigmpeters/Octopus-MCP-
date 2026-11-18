import httpx
import pytest

import server


class TrackedStream(httpx.SyncByteStream):
    def __init__(self, *chunks, before_chunk=None):
        self.chunks = chunks
        self.before_chunk = before_chunk
        self.reads = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            if self.before_chunk:
                self.before_chunk()
            yield chunk

    def close(self):
        self.closed = True


class TrackedTransport(httpx.MockTransport):
    closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def mock_transport(monkeypatch):
    def install(*responses):
        requests, clients = [], []
        pages = iter(responses)

        def respond(request):
            requests.append(request)
            return next(pages)

        client = httpx.Client

        def new_client(**kwargs):
            transport = TrackedTransport(respond)
            clients.append(transport)
            return client(transport=transport, **kwargs)

        monkeypatch.setattr(server.httpx, 'Client', new_client)
        monkeypatch.setattr(server, 'KEY', 'synthetic')
        monkeypatch.setattr(server, 'ACCOUNT', 'synthetic')
        return requests, clients

    return install


def standard_rates(product_code='TEST', tariff_code='E-1R-TEST-A'):
    return server.tariff_rates(product_code, tariff_code, 'electricity', '2025-03-30', '2025-03-30')


def test_client_reused_across_pages_and_tariff_categories(mock_transport):
    continuation = server.API + 'next/?page=2'
    requests, clients = mock_transport(
        httpx.Response(200, json={'results': [1], 'next': continuation}),
        httpx.Response(200, json={'results': [2]}),
        httpx.Response(200, json={'results': []}),
    )

    assert standard_rates('TEST+1', 'E-1R-TEST+1-A')['rates'] == {
        'standard-unit-rates': [1, 2], 'standing-charges': [],
    }
    assert len(clients) == 1 and clients[0].closed
    assert requests[0].url.raw_path.startswith(
        b'/v1/products/TEST%2B1/electricity-tariffs/E-1R-TEST%2B1-A/standard-unit-rates/?'
    )
    assert requests[0].url.params['period_from'] == '2025-03-30T00:00:00+00:00'
    assert requests[0].url.params['period_to'] == '2025-03-30T23:00:00+00:00'
    assert str(requests[1].url) == continuation
    assert requests[2].url.path.endswith('/standing-charges/')
    assert all(request.headers['Accept-Encoding'] == 'identity' for request in requests)


def test_request_budget_is_shared_across_rate_categories(mock_transport, monkeypatch):
    monkeypatch.setattr(server, 'REST_REQUEST_LIMIT', 1)
    requests, clients = mock_transport(
        httpx.Response(200, json={'results': []}),
        httpx.Response(200, json={'results': []}),
    )

    with pytest.raises(ValueError, match='request budget exceeded'):
        standard_rates()

    assert len(requests) == 1
    assert clients[0].closed
    assert server.tariff_products('2025-01-01T00:00:00Z')['products'] == []
    assert len(requests) == 2
    assert len(clients) == 2 and clients[1].closed


def test_consumption_account_lookup_and_readings_share_client(mock_transport):
    account = {'properties': [{'electricity_meter_points': [{
        'mpan': '123', 'meters': [{'serial_number': 'meter+1'}],
    }]}]}
    requests, clients = mock_transport(
        httpx.Response(200, json=account),
        httpx.Response(200, json={'results': []}),
    )

    result = server.consumption('electricity', '123', 'meter+1', '2025-10-26', '2025-10-26')

    assert result['coverage']['expected_interval_count'] == 50
    assert len(clients) == 1 and clients[0].closed
    assert requests[0].url.path == '/v1/accounts/synthetic/'
    assert requests[1].url.raw_path.startswith(b'/v1/electricity-meter-points/123/meters/meter%2B1/consumption/?')
    assert requests[1].url.params['period_from'] == '2025-10-25T23:00:00+00:00'
    assert requests[1].url.params['period_to'] == '2025-10-27T00:00:00+00:00'


def test_oversized_response_stops_streaming_and_closes(mock_transport, monkeypatch):
    monkeypatch.setattr(server, 'REST_RESPONSE_BYTES', 10)
    stream = TrackedStream(b'12345678', b'9012', b'3456')
    requests, clients = mock_transport(httpx.Response(200, stream=stream))

    with pytest.raises(ValueError, match='response is too large'):
        standard_rates()

    assert len(requests) == 1
    assert stream.reads == 2 and stream.closed
    assert clients[0].closed


def test_response_budget_is_shared_across_rate_categories(mock_transport, monkeypatch):
    empty_page = b'{"results":[]}'
    monkeypatch.setattr(server, 'REST_TOTAL_BYTES', len(empty_page) + 4)
    stream = TrackedStream(empty_page[:4], empty_page[4:], b' ')
    requests, clients = mock_transport(
        httpx.Response(200, content=empty_page),
        httpx.Response(200, stream=stream),
    )

    with pytest.raises(ValueError, match='response budget exceeded'):
        standard_rates()

    assert len(requests) == 2 and len(clients) == 1
    assert stream.reads == 2 and stream.closed
    assert clients[0].closed


def test_slow_stream_exhausts_shared_time_budget(mock_transport, monkeypatch):
    elapsed = 0

    def advance_clock():
        nonlocal elapsed
        elapsed += 16

    monkeypatch.setattr(server, 'monotonic', lambda: elapsed)
    first = TrackedStream(b'{"results":[]}', before_chunk=advance_clock)
    second = TrackedStream(b'{"results":', b'[]}', b' ', before_chunk=advance_clock)
    requests, clients = mock_transport(
        httpx.Response(200, stream=first),
        httpx.Response(200, stream=second),
    )

    with pytest.raises(ValueError, match='time budget exceeded'):
        standard_rates()

    assert len(requests) == 2 and len(clients) == 1
    assert requests[0].extensions['timeout']['read'] == 30
    assert requests[1].extensions['timeout']['read'] == 29
    assert first.closed
    assert second.reads == 2 and second.closed
    assert clients[0].closed


def test_unexpected_content_encoding_is_rejected_before_reading(mock_transport):
    stream = TrackedStream(b'encoded response')
    _, clients = mock_transport(httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=stream))

    with pytest.raises(ValueError, match='Unexpected encoding'):
        standard_rates()

    assert stream.reads == 0 and stream.closed
    assert clients[0].closed
