# Working on Octopus MCP

Maintain a private, read-only source of Octopus household data. Clients use the returned intervals, units and published rates for pricing and simulation. Start with the [architecture](docs/ARCHITECTURE.md), [accepted decisions](docs/DECISIONS.md) and [current roadmap](docs/ROADMAP.md).

## Set up and verify

From the repository root, use Python 3.12, matching CI and the container.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

Tests use synthetic fixtures and mocked upstream calls. They run without an Octopus account or tunnel. Use the [deployment guide](README.md) for private end-to-end checks and keep credentials, raw household responses and identifying logs out of commits and PRs.

## Changing a tool

1. Locate the registration and helper in [server.py](server.py). Preserve existing MCP names, parameters, response keys and their meanings. In particular, callers consume the flat meter list as well as supply-point metadata. Document additions and any intentional compatibility change.
2. Validate user inputs before issuing requests. For consumption, verify that the fuel, point and serial belong together in the configured account. Keep import, export and gas distinct. Report ambiguous meter candidates even when a single agreement is active. Extend [meter discovery tests](tests/test_meter_discovery.py) for selection changes.
3. Convert inclusive UK dates to half-open UTC windows. Keep coverage explicit across short, ordinary and long UK days. Preserve unknown gas units and distinguish a metadata lookup failure from a meter with no unit. Exercise dates, pagination, gaps, duplicates and ownership in [consumption tests](tests/test_consumption.py).
4. Preserve price validity, VAT fields, units, payment methods and empty rate categories. Catalogue availability alone cannot establish eligibility. Four published EV bands do not establish dispatch or daily switching hours. Extend [tariff tests](tests/test_tariff_discovery.py) when changing endpoints or return shapes.
5. Add synthetic success and failure cases at the boundary being changed. Test HTTP destination and credential behavior with a mocked transport beneath the adapter. Mocking the entire GET helper bypasses those checks. Run the full suite and update relevant docs in the same PR.

## Prioritized follow-up work

1. **Reject malformed pages.** Require an object containing a results list for consumption and standard tariffs. Keep legitimate empty lists meaningful. Cover absent and ill-typed results, repeated continuations and malformed JSON with short errors that omit identifiers. Share page validation with the catalogue and other rate helpers where their contracts agree.
2. **Verify multi-day readings.** The roadmap records a change to default upstream ordering after overlapping pages were observed. On an authorized private deployment, record the deployed revision, compare a seven-day request with daily coverage for the same window, and check ordering, duplicates and gaps. Record aggregate outcomes by fuel and direction without copying live data. Mark only the cases actually checked.
3. **Bound transport work.** Reuse an HTTPX client across pages within a tool call. Bound response bytes and cumulative work across rate categories. Use mocked oversized or slow pages to verify early termination and cleanup. Consolidate date-window and identifier handling with compatibility tests as those paths change.

Keep PRs small and distinguish mocked coverage from deployed behavior. Review CI before merge. A PR build validates packaging. Publishing and updating a running instance are separate release steps. Prioritize later tariff applicability, telemetry and simulation work according to the [roadmap](docs/ROADMAP.md).
