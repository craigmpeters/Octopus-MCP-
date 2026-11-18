import httpx
import pytest

import server


@pytest.mark.parametrize('continuation, allowed', [
    ('https://api.octopus.energy:443/v1/products/?page=2', True),
    ('https://api.oegb-kraken.energy/v1/products/?page=2', False),
    ('//other.example/products/', False),
    ('http://api.octopus.energy/v1/products/', False),
    ('https://api.octopus.energy:444/v1/products/', False),
    ('https://someone@api.octopus.energy/v1/products/', False),
])
def test_catalogue_continuation_origin(monkeypatch, continuation, allowed):
    requests = []

    def respond(request):
        requests.append(request)
        page = len(requests)
        return httpx.Response(200, json={
            'results': [page], 'next': continuation if page == 1 else None,
        })

    transport = httpx.MockTransport(respond)
    client = httpx.Client
    monkeypatch.setattr(server.httpx, 'Client', lambda **kw: client(transport=transport, **kw))
    monkeypatch.setattr(server, 'KEY', 'synthetic')
    monkeypatch.setattr(server, 'ACCOUNT', 'synthetic')
    instant = '2025-01-01T00:00:00Z'
    if allowed:
        assert server.tariff_products(instant)['products'] == [1, 2]
        assert requests[1].url.params['page'] == '2'
    else:
        with pytest.raises(ValueError, match='^Unexpected API pagination URL$'):
            server.tariff_products(instant)
        assert len(requests) == 1
    assert all(r.url.host == 'api.octopus.energy' and
               r.headers['Authorization'].startswith('Basic ') for r in requests)
