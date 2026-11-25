import asyncio
import json

import httpx
import pytest

import server


def test_statement_lookup_uses_configured_account_through_mcp(monkeypatch):
    row = {'id': 'tx1', 'kind': 'Charge', 'postedDate': '2026-02-14', 'title': 'EV charging',
           'note': 'Electric Juice', 'reasonCode': None, 'isReversed': False,
           'amounts': {'net': 100, 'tax': 20, 'gross': 120}}

    def respond(request):
        assert request.url == httpx.URL(server.GRAPHQL_API)
        payload = json.loads(request.content)
        if 'obtainKrakenToken' in payload['query']:
            assert 'Authorization' not in request.headers
            return httpx.Response(200, json={'data': {'obtainKrakenToken': {'token': 'mock-token'}}})
        assert request.headers['Authorization'] == 'mock-token'
        assert payload['variables'] == {'account': 'mock-account', 'id': '42', 'after': 'first'}
        page = {'edges': [{'node': row}], 'pageInfo': {'hasNextPage': True, 'endCursor': 'second'}}
        bill = {'id': '42', 'billType': 'STATEMENT', '__typename': 'StatementType',
                'issuedDate': '2026-03-01', 'transactions': page}
        return httpx.Response(200, json={'data': {'account': {'bill': bill}}})

    client = httpx.Client
    monkeypatch.setattr(server.httpx, 'Client', lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(server, 'KEY', 'mock-key')
    monkeypatch.setattr(server, 'ACCOUNT', 'mock-account')
    content = asyncio.run(server.mcp.call_tool('statement_transactions', {'statement_id': '42', 'after': 'first'}))
    result = json.loads(content[0].text)
    assert result == {'statement_id': '42', 'issued_date': '2026-03-01',
                      'amount_unit': 'minor currency units', 'records': [row], 'next_cursor': 'second'}


@pytest.fixture
def period_bill(monkeypatch):
    bill = {'id': '42', 'billType': 'STATEMENT', '__typename': 'PeriodBasedDocumentType',
            'issuedDate': '2026-03-01', 'documentTransactions': {
                'edges': [], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
    monkeypatch.setattr(server, 'graphql_token', lambda: 'mock-token')
    monkeypatch.setattr(server, 'graphql_request', lambda *args: {'account': {'bill': bill}})
    return bill


def test_period_statement_empty_final_page(period_bill):
    result = server.statement_transactions('42')
    assert result['records'] == []
    assert result['next_cursor'] is None


@pytest.mark.parametrize('override', [{'id': 'other'}, {'billType': 'INVOICE'}, {'issuedDate': None},
                                      {'documentTransactions': None}, {'documentTransactions': {
                                          'edges': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}}}])
def test_unavailable_statement_or_bad_page(period_bill, override):
    period_bill.update(override)
    with pytest.raises(ValueError, match='unavailable for this account'):
        server.statement_transactions('42', 'same')


@pytest.mark.parametrize('statement_id,after', [(' ', None), ('42', '')])
def test_bad_input_before_token_exchange(monkeypatch, statement_id, after):
    monkeypatch.setattr(server, 'graphql_token', lambda: pytest.fail('unexpected token request'))
    with pytest.raises(ValueError, match='Provide a statement ID'):
        server.statement_transactions(statement_id, after)
