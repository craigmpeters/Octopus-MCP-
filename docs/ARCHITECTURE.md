# Octopus MCP architecture

Octopus MCP serves one configured Octopus Energy account. Clients retrieve interval readings, meter metadata and published prices for analysis in ChatGPT or Jupyter. The Python process has no application database. Tool results, including household identifiers and usage, travel back to the client and are subject to its retention settings.

## Running system

```mermaid
flowchart LR
    Client[ChatGPT] --> Tunnel[OpenAI Secure MCP Tunnel]
    Tunnel --> Host["Host loopback · port 8765"]
    Local[Local MCP client] --> Host
    Host --> Service["FastMCP /mcp · container port 8000"]
    Service -->|Account, consumption, products and rates| REST[Octopus REST API]
    Service -->|Token exchange and gas unit lookup| Kraken[Kraken GraphQL API]
```

The tunnel is configured separately by the operator. Compose publishes the container's `0.0.0.0:8000` listener on `127.0.0.1:8765`. FastMCP serves stateless Streamable HTTP with JSON responses. The application has no caller authentication. Any caller with network access to the listener can use the configured account, including peers that can reach the container directly. Meter ownership checks limit the selected meter to that account. The deployment guide covers tunnel setup and verification. [README](../README.md)

### Tool surface

The seven async MCP tools and their domain logic live in [server.py](../server.py). They share a request-scoped REST and GraphQL adapter in [upstream.py](../upstream.py).

| Tool | Data flow and result |
| --- | --- |
| `list_meters` | Reads account properties and groups meter candidates and agreements by supply point. Returns the compatible flat meter list alongside selection metadata. |
| `consumption` | Matches fuel, point and serial against the account inventory before fetching readings. Returns sorted half-hours, coverage gaps, overlapping agreements and measurement metadata. |
| `tariff_products` | Pages through published products at a timezone-aware instant. Household eligibility is unknown. |
| `tariff_product` | Retrieves one product and its regional variants. |
| `tariff_rates` | Retrieves standard unit rates and standing charges for electricity or gas. |
| `tariff_dual_rates` | Retrieves electricity day, night and standing-charge records. |
| `tariff_ev_rates` | Retrieves four published electricity rate bands and standing charges, with source URLs and empty categories. |

Consumption and rate requests accept up to 31 inclusive UK dates. Local midnight boundaries in `Europe/London` define a half-open UTC window. Consumption excludes out-of-window readings, rejects duplicate or misaligned half-hours and represents gaps explicitly. A UK day can contain 46, 48 or 50 half-hours. Agreement validity and physical meter installation dates are separate facts. Multiple serials can remain ambiguous even when one agreement is active.

Electricity consumption is in kWh. Gas readings retain the reported unit where available. A failed metadata lookup returns readings with a unit status of `lookup_failed`, while an absent meter unit yields `unavailable_for_meter`. Clients combine usage and prices, preserving VAT basis, validity periods, payment method, and the distinction between pence/kWh and pence/day. Published bands alone cannot establish switching hours or account-specific EV dispatch.

### Credentials, requests and failures

The process reads `OCTOPUS_ACCOUNT_NUMBER` and `OCTOPUS_API_KEY` at startup. REST GETs use HTTP Basic authentication against the Octopus API. For gas metadata, the service posts the key to the fixed Kraken GraphQL token endpoint, then sends the returned token in the Authorization header to that same endpoint to query the account. This token exchange supports read-only energy queries.

Each tool call owns one HTTPX client and a 60-second deadline for upstream I/O. The adapter disables redirects and accepts REST continuations only on the original HTTPS origin. It attaches Basic auth per REST request. The separate fixed GraphQL endpoint receives only the credentials needed for each GraphQL operation. Request URLs can contain account numbers, meter points and serials, so treat logs as sensitive.

The adapter requests identity encoding and streams each response, with limits of 4 MiB per body, 16 MiB across the call and 20 pages per collection. The call budget covers account discovery, pagination, gas metadata and all requested rate categories. Transport failures, invalid JSON, missing results lists and invalid continuations produce short errors. An empty results list is valid. The optional gas unit lookup can fail independently of reading retrieval.

### Packaging and release

The Python 3.12 image runs under UID/GID 65534. Compose sets a read-only filesystem, drops Linux capabilities and enables no-new-privileges. CI runs pytest on pushes and pull requests. Container PR builds targeting main build the image locally on the runner. Pushes to main and manual workflow runs publish linux/amd64 images to GHCR tagged with the commit SHA and latest. Updating the running Docker host is a separate operator action. [Container workflow](../.github/workflows/container.yml) · [Compose configuration](../compose.yaml)

## Target design

Extract modules incrementally as changes create a reason to do so. Keep tool registration in the server, isolate transport and credential handling in a client, and group meter selection, interval coverage, UK time windows, tariff discovery and rate normalization by responsibility. Share normalized models where callers need stable contracts. Any future retries for transient failures must fit the same per-call deadline and byte budget.

A future optional Home Assistant adapter would supply allowlisted solar, EV charger and battery telemetry using protected, minimal-access credentials. Keep measured and inferred quantities distinct. Pricing and battery simulation belong in clients. Device control requires its own authorization and safety design. The roadmap tracks live verification and feature status. [Decisions](DECISIONS.md) · [Roadmap](ROADMAP.md)
