# Target Architecture

## Data flow

```text
ChatGPT or Jupyter (questions, analysis, decisions)
  |
  v
OpenAI Secure MCP Tunnel (private transport)
  |
  v
Octopus MCP service (FastMCP; read-only by default)
  |-- Tool/API layer: stable, documented MCP interfaces
  |-- Data access adapters
  |    |-- Octopus REST API: account, meters, consumption, products, rates
  |    |-- Optional Home Assistant: solar, charger, battery and household sensors
  |-- Domain services
  |    |-- Meter discovery, direction and time-bounded selection
  |    |-- Interval normalization, UK timezone and coverage
  |    |-- Tariff catalogue, eligibility and rate normalization
  |    |-- Solar, export and EV data discovery
  |-- Validation, structured errors and provenance
```

## Boundaries

**Interface:** MCP tools return source records with units, provenance, coverage, timestamps and limitations. The same data can support analysis in ChatGPT or a Jupyter notebook.

**Octopus adapter:** authenticated read-only HTTP requests with bounded timeouts/retries, safe pagination and redacted errors. Do not allow arbitrary user-provided URLs or cross-origin pagination.

**Home Assistant adapter (planned):** optional, explicitly configured, minimal-access telemetry. Prefer read-only access and explicit entity allowlists; never expose HA to the public internet to make this work. A Home Assistant token may allow writes despite the plugin only issuing GETs, so protect it accordingly.

**Client analysis:** ChatGPT, Jupyter or another client can price usage, compare tariffs and simulate batteries. Preserve interval granularity at the MCP boundary so clients can join usage and rates without losing time-of-use detail.

**Deployment:** private Docker network and Secure MCP Tunnel; no unauthenticated public MCP endpoint. Keep the existing container hardening (non-root, read-only filesystem, no-new-privileges, dropped capabilities) and verify tunnel/client networking on the actual deployment.

## Temporal and units model

- Store/compare energy intervals as timezone-aware UTC start/end instants; group reports by `Europe/London` local dates.
- UK clock changes produce 46 or 50 half-hour intervals on transition days; do not assume 48 every day.
- Missing readings are **unknown**, not zero. Detect duplicates, gaps, out-of-window data and ambiguous meter selections.
- Electricity import/export energy: kWh. Gas readings: retain original unit; convert only with validated unit and conversion inputs.
- Tariff rates: distinguish VAT-inclusive/exclusive, pence/kWh, pence/day, import/export and time applicability.
- Track meter validity and tariff agreement validity separately. An active agreement does not alone prove a particular physical meter is installed.
- Return import, export, gas and standing-charge data separately so clients can combine them when appropriate.

## Security and privacy

- Secrets via deployment environment/secret management, never repository files, logs, errors or test fixtures.
- Validate account ownership of requested meters; do not expose identifiers unnecessarily in summaries.
- Limit date ranges, response sizes and pagination; retry only transient failures.
- Treat Octopus and Home Assistant API responses as untrusted external data.
- Default to read-only. Any future device control requires a separate design, explicit authorization and safety limits.
- Keep GHCR publication and production deployment separate: opening a PR must not deploy; merge/release should be deliberate.

## Proposed module boundaries (not all implemented)

```text
octopus_mcp/
  server.py           # MCP registration
  client.py           # Octopus API adapter
  meters.py           # Meter identity, import/export and validity
  consumption.py      # Retrieval and coverage
  time_utils.py       # Europe/London/UTC handling
  models.py           # Normalized schemas
  tariffs.py          # Catalogue and eligibility
  rates.py            # Rate normalization
  home_assistant.py   # Optional read-only telemetry
  solar.py            # Solar and export telemetry
  ev.py               # EV and dispatch data
```

Refactor incrementally; do not require a wholesale rewrite before delivering tested improvements.
