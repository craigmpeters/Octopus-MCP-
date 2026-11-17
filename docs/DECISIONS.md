# Architecture Decision Record (ADR) Index

These decisions are accepted as **project design targets**, not claims of completed implementation. Revisit them when new evidence appears.

## ADR-001 — GitHub documentation is the durable project context
**Status:** Accepted (2026-11-17)

Use versioned documentation in `docs/` to carry vision, decisions and roadmap between ChatGPT, Codex and contributors. Update docs in the same PR as relevant implementation changes.

## ADR-002 — Private, read-only-first MCP
**Status:** Accepted (2026-11-17)

Keep the MCP service private behind the Secure MCP Tunnel, not publicly exposed without proper authentication. Read-only account, meter, tariff and telemetry access is the default. Device control is out of scope until separately designed and explicitly approved.

## ADR-003 — Deterministic analysis, not ad hoc LLM arithmetic
**Status:** Accepted (2026-11-17)

Perform pricing, time-series alignment, tariff comparison and battery simulations in tested Python domain code. Use ChatGPT for interpretation and natural-language interaction. Show inputs, assumptions and uncertainty.

## ADR-004 — Octopus is billing data; Home Assistant is optional telemetry
**Status:** Accepted (2026-11-17)

Octopus provides account, import/export, gas and tariff data. Home Assistant can supplement solar generation, EV charger and future battery measurements if configured. Do not infer device-level energy consumption from whole-home import readings.

## ADR-005 — Meter, direction, date and units must be explicit
**Status:** Accepted (2026-11-17)

Treat electricity import, electricity export and gas independently. Preserve physical meter history and tariff agreement history; flag ambiguous current meter selection. Use UTC intervals with Europe/London local reporting and handle DST. Never treat missing readings as zero or silently assume gas kWh.

## ADR-006 — Honest tariff comparison and eligibility
**Status:** Accepted (2026-11-17)

Compare only tariffs that can be supported by rate and eligibility data. Separate historical replay from future forecasts. Account for standing charges, VAT, export, regional variation and special EV dispatch adjustments where verified. Clearly mark incomplete estimates.

## ADR-007 — Small PRs, CI and controlled releases
**Status:** Accepted (2026-11-17)

Keep compatibility with existing MCP tools where practical. Add automated tests and CI checks before shipping pricing logic. PR creation is not authorization to merge, publish a production image or deploy to OpenMediaVault.

## ADR-008 — Battery is simulated before integrated
**Status:** Accepted (2026-11-17)

Because the home battery is planned, first model candidate capacities, efficiency, charge/discharge power, solar surplus, tariff arbitrage and installed cost. Do not imply the battery already exists or present simulated savings as guaranteed.
