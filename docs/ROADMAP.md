# Roadmap

This roadmap is prioritized, not a claim of completed features. Each phase should be a separately reviewable PR or small series of PRs.

## Phase 0 — Baseline and deployment validation
**Status:** Existing minimal implementation; live validation incomplete.

- Verify `list_meters` and existing MCP connectivity.
- Confirm private tunnel and container restart/health behaviour.
- Verify Octopus responses without recording secrets or private identifiers.
- Preserve the existing `list_meters`, `consumption` and `tariff_rates` tools.

## Phase 1 — PR #2: Meter reliability and consumption validation
**Priority:** Critical. **Status:** Planned; `feature/meter-reliability` branch exists.

- Identify electricity import, electricity export and gas separately, including historical meters and date-relevant agreements.
- Report ambiguous current meter candidates instead of guessing.
- Validate account ownership, intervals, duplicates, gaps, pagination and API errors.
- Correctly handle 48/46/50 half-hour UK days and gas unit metadata.
- Add mocked import/export/gas/DST tests and GitHub Actions test gate.
- **Done when:** each fuel/direction can be queried independently, completeness is explicit, tests pass and read-only live validation has been performed.

## Phase 2 — PR #3: Tariff discovery and comparison
**Priority:** High. **Status:** Planned.

- Retrieve products, regional tariff variants, account agreements and relevant rate structures.
- Distinguish tariff existence from household eligibility; identify missing eligibility information.
- Build interval-level deterministic cost replay: import + standing charges - export earnings; gas separate.
- Include VAT, day/night and time-of-use rates, plus supported special EV dispatch adjustments.
- **Done when:** historical tariff comparison produces auditable results with coverage, assumptions and limitations; no unsupported claim of actual billed cost.

## Phase 3 — PR #4: Solar and EV insights
**Priority:** High. **Status:** Planned.

- Report import/export separately, and calculate export revenue from verified rates.
- Add optional read-only Home Assistant adapter with explicit entity mapping and protected credentials.
- Use solar generation telemetry to estimate self-consumption; reconcile sampling intervals and energy units.
- Add EV charging energy from verified charger telemetry and Octopus device/dispatch data where officially supported.
- **Done when:** solar and EV cost analyses distinguish measured values from inferred/estimated values.

## Phase 4 — PR #5: Battery simulation
**Priority:** Medium. **Status:** Planned.

- Simulate candidate battery capacities and usable energy, power limits, round-trip efficiency, degradation and installed cost.
- Compare solar self-consumption, off-peak grid charging and export tradeoffs under verified tariffs.
- Show annual savings, payback and sensitivity to uncertain future prices.
- **Done when:** repeatable tests validate energy conservation and cost calculations across representative scenarios.

## Phase 5 — Recommendations and automation
**Priority:** Later. **Status:** Exploratory.

- Suggest cheapest charging windows, tariff switching opportunities and solar/battery strategies.
- Add data-quality alerts and bill-audit checks where supported.
- Consider Home Assistant device control only after a separate security/authorization ADR; no implicit control.

## Open questions / dependencies

- Which EV and charger models are present? Which Home Assistant entities measure charger kWh?
- Which solar inverter/integration is installed, and does HA expose reliable generation and export data?
- Which Octopus tariff(s), regional tariff codes and export arrangements apply?
- Are authenticated Octopus device/Intelligent dispatch APIs officially available for this account?
- What battery candidates, installed prices and usable capacities should be modelled?

## Rules for claiming completion

Do not mark a phase complete because code was drafted. Require code review, passing CI, clear documentation, and (where relevant) live read-only verification with real data. Do not commit live API responses or private household identifiers.
