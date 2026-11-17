# Octopus MCP — Project Context

> Canonical context for future ChatGPT, Codex and human contributors. Read this document together with [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md) and [ROADMAP.md](ROADMAP.md) before proposing changes. These files record intentions, not proof that a feature has been implemented.

## Vision

Build a personal, read-only-first Octopus Energy MCP service that helps answer:
- What am I paying for electricity import, electricity export and gas?
- Which **eligible** Octopus tariff would be cheapest for my **actual** household usage?
- How much do solar generation and export save or earn?
- What does EV charging cost, including applicable intelligent charging adjustments?
- Would a home battery save money, and what capacity is economically sensible?
- What should I shift to cheaper periods, based on measured data and explicit assumptions?

## Household context (non-secret)

- Solar panels: installed.
- Home battery: planned, not yet installed.
- Electric vehicle: yes; vehicle and charger models not yet established.
- Home Assistant: yes; available entities and integrations not yet established.
- Location: United Kingdom. Do not assume a specific electricity distribution region, postcode, meter identifiers or tariff.
- Never commit Octopus credentials, account numbers, MPANs/MPRNs, meter serials, Home Assistant tokens or private entity data.

## Existing baseline (as reviewed 2026-11-17)

- Python FastMCP server in `server.py` with `list_meters`, `consumption`, `tariff_rates`, `tariff_products`, `tariff_product`, `tariff_dual_rates`, and `tariff_ev_rates`.
- Octopus REST API via `httpx`; electricity import/export and gas meters can appear in account discovery.
- `consumption` accepts a selected meter point and serial number and fetches up to 31 inclusive UK calendar dates.
- `tariff_rates` currently reads standard unit rates and standing charges only; it is **not** a complete tariff comparison engine.
- Docker deployment via GHCR on OpenMediaVault, accessed privately using an OpenAI Secure MCP Tunnel.
- Existing implementation must be checked against current `main` before making assumptions; live end-to-end consumption, export, gas and tariff-rate validation is not yet established.
- A separate branch `feature/meter-reliability` was created for planned work. This documentation PR does not implement those changes.

## Source of truth and working method

1. Read current code and docs; verify what exists versus what is planned.
2. Propose small, testable changes and preserve existing MCP tool compatibility where possible.
3. Use feature branches and PRs; do not merge or deploy without explicit instruction.
4. Use mocked fixtures for CI, then perform separate privacy-conscious live read-only validation.
5. Update these docs when architecture, assumptions, security posture or roadmap change.
6. Label estimates, missing data and unsupported tariff features clearly; never invent prices or device readings.
7. For new or changed MCP tools, follow the [OMV deployment and ChatGPT refresh steps](../README.md#deploy-and-refresh-new-mcp-tools) and verify a call to a new or changed tool.

## Important distinctions

- MCP provides reusable data and its provenance. ChatGPT, Jupyter or another client performs cost calculations, comparisons and simulations using that data.
- Octopus import/export meter data does **not** directly measure solar generation or EV charging consumption.
- Home Assistant can provide supplementary telemetry **only if relevant entities exist** and are configured.
- Intelligent Octopus dispatch and other special charging adjustments require supported, verified data sources; standard tariff rates alone are insufficient.
- A published Octopus tariff is not necessarily available or eligible for the household.
- Gas meter readings may use volume units; conversion to kWh requires appropriate conversion parameters and assumptions.
- Battery economics are simulations, not guaranteed savings.
