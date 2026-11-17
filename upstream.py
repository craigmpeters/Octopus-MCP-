"""Per-tool HTTP transport for Octopus REST and Kraken GraphQL."""
import asyncio
import json
from contextlib import asynccontextmanager

import httpx

API = 'https://api.octopus.energy/v1/'
GRAPHQL_API = 'https://api.oegb-kraken.energy/v1/graphql/'
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CALL_BYTES = 16 * 1024 * 1024
CALL_TIMEOUT_SECONDS = 60


def rest_url(path, base=API):
    try:
        url = httpx.URL(base).join(path)
    except (httpx.InvalidURL, ValueError):
        raise ValueError('Invalid REST pagination URL') from None
    if (url.scheme, url.host, url.port) != ('https', 'api.octopus.energy', None) or url.userinfo:
        raise ValueError('Unexpected REST pagination origin')
    return url


class Upstream:
    def __init__(self, client, key, account):
        self.client = client
        self.key = key
        self.account = account
        self.remaining_bytes = MAX_CALL_BYTES

    async def _request_json(self, method, url, **kwargs):
        if not self.key or not self.account:
            raise ValueError('Set OCTOPUS_API_KEY and OCTOPUS_ACCOUNT_NUMBER on the server.')
        if self.remaining_bytes <= 0:
            raise ValueError('Octopus response size limit exceeded')
        body = bytearray()
        async with self.client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            # Read identity bytes so a compressed chunk cannot expand past the budget.
            if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ValueError('Unexpected Octopus response encoding')
            async for chunk in response.aiter_raw():
                if len(chunk) > min(MAX_RESPONSE_BYTES - len(body), self.remaining_bytes):
                    raise ValueError('Octopus response size limit exceeded')
                self.remaining_bytes -= len(chunk)
                body.extend(chunk)
        try:
            return json.loads(body)
        except (ValueError, RecursionError):
            raise ValueError('Invalid JSON in Octopus response') from None

    async def get(self, path, params=None):
        try:
            return await self._request_json('GET', rest_url(path), params=params, auth=(self.key, ''))
        except httpx.HTTPStatusError as exc:
            raise ValueError(f'Octopus API returned HTTP {exc.response.status_code}; check account, access and requested data.') from None
        except httpx.RequestError:
            raise ValueError('Unable to reach the Octopus API; try again later.') from None

    async def graphql_request(self, query, variables, token=None):
        headers = {'Authorization': token} if token else None
        try:
            payload = await self._request_json('POST', GRAPHQL_API, headers=headers,
                                              json={'query': query, 'variables': variables})
        except (httpx.HTTPError, ValueError):
            raise ValueError('Unable to retrieve Octopus GraphQL metadata') from None
        if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('data'), dict):
            raise ValueError('Unable to retrieve Octopus GraphQL metadata')
        return payload['data']

    async def rows(self, path, params):
        rows = []
        seen = set()
        for _ in range(20):
            page = await self.get(path, params)
            if not isinstance(page, dict) or not isinstance(page.get('results'), list):
                raise ValueError('Invalid results list in Octopus response')
            rows.extend(page['results'])
            continuation = page.get('next')
            if continuation is None:
                return rows
            if not isinstance(continuation, str) or not continuation.strip():
                raise ValueError('Invalid Octopus pagination')
            path = str(rest_url(continuation, rest_url(path)))
            if path in seen:
                raise ValueError('Repeated Octopus pagination URL')
            seen.add(path)
            params = None
        raise ValueError('Too many Octopus pages; request a shorter period')


@asynccontextmanager
async def upstream_call(key, account):
    try:
        async with asyncio.timeout(CALL_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=30, follow_redirects=False,
                                         headers={'Accept-Encoding': 'identity'}) as client:
                yield Upstream(client, key, account)
    except TimeoutError:
        raise ValueError('Octopus request deadline exceeded') from None
