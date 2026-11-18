# Roadmap

This roadmap is prioritized, not a claim of completed features. Each phase should be a separately reviewable PR or small series of PRs.

## Phase 0 — Baseline and deployment validation
**Status:** Existing minimal implementation; live validation incomplete.

- Verify `list_meters` and existing MCP connectivity.
- Confirm private tunnel and container restart/health behaviour.
- Verify Octopus responses without recording secrets or private identifiers.
- Preserve the existing `list_meters`, `consumption` and `tariff_rates` tools.

## Phase 1 — PR #2: Meter reliability and consumption validation
**Priority:** Critical. **Status:** In progress. Consumption validation, coverage reporting and meter discovery have passed targeted live checks. Consumption responses include date-relevant agreements and resolve gas units through Kraken GraphQL `consumptionUnits`, falling back to an explicit unknown state for lookup failures or omitted historical meters. Physical meter validity dates remain unavailable.

- Identify electricity import, electricity export and gas separately, including historical meters and date-relevant agreements.
- Report ambiguous current meter candidates instead of guessing.
- Validate account ownership, intervals, duplicates, gaps, pagination and API errors.
- Correctly handle 48/46/50 half-hour UK days and gas unit metadata.
- Add mocked import/export/gas/DST tests and GitHub Actions test gate.
- **Done when:** each fuel/direction can be queried independently, completeness is explicit, tests pass and read-only live validation has been performed.

Live sampling across both ambiguous import and gas candidates found complete readings on one candidate for selected 2025–2026 dates, but no readings on either candidate for selected 2023–2024 dates. Consumption availability therefore does not establish historical installation dates and must not be used to label a candidate as the current physical meter.

## Phase 2 — Tariff data for comparison
**Priority:** High. **Status:** In progress. Catalogue discovery and published dual-register rates passed live checks through MCP.

- Retrieve products, regional tariff variants, account agreements and relevant rate structures.
- Distinguish tariff existence from household eligibility; identify missing eligibility information.
- Expose VAT basis, day/night and time-of-use rates, and verified EV dispatch data with their sources and time bounds.
- **Done when:** clients can retrieve the usage, price and applicability data needed for an auditable comparison with gaps and limitations visible. Clients calculate costs and savings.

`tariff_products` and `tariff_product` expose published catalogue discovery and regional variants. `tariff_dual_rates` exposes day/night rates and standing charges. For products listed under `four_rate_ev_electricity_tariffs`, `tariff_ev_rates` retrieves separate household and EV rate bands from the published endpoints. A current four-rate Intelligent Octopus product returned those bands even though its standard endpoint returned no unit rates. Household eligibility, switching schedules, and account-specific EV dispatch applicability still require separate evidence.

The private deployment successfully queried Kraken's `applicableRates` for its electricity import supply point. The one-day sample had four rows, two distinct values and three overlapping rows. The combined intervals covered the full day. Rate precedence, units, VAT basis and EV dispatch applicability still need verification before exposing these rates through MCP. [Diagnostic and live result](TARIFF_APPLICABILITY.md)

## Phase 3 — PR #4: Solar and EV insights
**Priority:** High. **Status:** In progress. Separate electricity import and export readings and the export tariff's published rate passed a live check.

- Provide separate import and export readings and verified export rates for client calculations.
- Add optional read-only Home Assistant adapter with explicit entity mapping and protected credentials.
- Use solar generation telemetry to estimate self-consumption; reconcile sampling intervals and energy units.
- Add EV charging energy from verified charger telemetry and Octopus device/dispatch data where officially supported.
- **Done when:** solar and EV cost analyses distinguish measured values from inferred/estimated values.

A live MCP check for 8–14 November 2026 returned 336 complete import readings and 336 complete export readings from separate requests. The export agreement covered the sample window and matched the product's published regional variant. Exactly one published standard unit rate covered every export reading. This check covered one agreement and verified the published prices used for an estimate. [Export estimate workflow](../README.md#estimate-export-credit)

## Phase 4 — Data for client-side battery simulation
**Priority:** Medium. **Status:** Planned.

- Identify source data for battery capacities, usable energy, power limits, efficiency, degradation and installed cost.
- Make usage, generation, import and export rate inputs available for simulations in Jupyter or another client.
- **Done when:** a client can retrieve traceable inputs for representative battery scenarios.

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

### Live validation note (2026-11-17)

Single-day import, export and gas requests returned 48 intervals on a normal day and 50 on the autumn clock-change day. A seven-day request failed duplicate detection for all three, so daily requests were used as a workaround.

A subsequent seven-day electricity API diagnostic found 64 overlapping intervals with `order_by=period` and zero with the default ordering. The implementation switched to default upstream ordering and sorts the results locally. The cause of the overlapping pages remains unknown.

### Live multi-day validation (2026-11-18)

Through the private MCP connection, a seven-day `consumption` request for 8–14 November 2026 was compared with seven single-day requests for the same UK dates and meter. For import and gas, one of the two discovered candidates returned readings on the first day and was used for the comparison. The export point had one candidate. Physical meter validity remains unknown.

| Supply | Seven-day intervals | Daily intervals combined | Gaps | Duplicates | Out of order |
| --- | ---: | ---: | ---: | ---: | ---: |
| Electricity import | 336 | 336 | 0 | 0 | 0 |
| Electricity export | 336 | 336 | 0 | 0 | 0 |
| Gas | 336 | 336 | 0 | 0 | 0 |

All seven daily responses returned 48 readings for each supply. Interval timestamps and reported consumption values matched between weekly and daily requests, and every response reported complete coverage. This multi-day check covered one candidate per supply and a week of 48-interval days.

The operator reported deploying PR #16 before the checks. The image for merge commit `432e8bb2025ec4d5cbd9785d8d1a45cbdecc3a26` was published successfully. The running container's image ID was unavailable through MCP. [Publish run](https://github.com/craigmpeters/Octopus-MCP-/actions/runs/44371895087)
