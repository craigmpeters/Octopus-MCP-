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

Use the [roadmap](docs/ROADMAP.md) to pick the next tariff applicability, telemetry or simulation task. The [architecture](docs/ARCHITECTURE.md#credentials-requests-and-failures) documents the REST limits shared across pages and rate categories.

The roadmap records the [live multi-day consumption checks](docs/ROADMAP.md#live-multi-day-validation-2026-11-18) for electricity import, electricity export and gas.

Keep PRs small and distinguish mocked coverage from deployed behavior. Review CI before merge. A PR build validates packaging. Publishing and updating a running instance are separate release steps.
