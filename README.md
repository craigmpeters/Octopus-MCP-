# Personal Octopus Energy MCP — first version

A personal, read-only MCP server: list meters and tariff agreements, fetch electricity/gas consumption, and fetch standard unit rates and standing charges. It does not control charging or change account settings. Data is fetched directly from Octopus; no database or account data is deliberately stored by this app. ChatGPT may retain tool results according to your settings.

## 1. Set up on your Docker host

Use the repository's `compose.yaml` as a template. It names both the Compose service and the Docker container `octopusmcp`. On OpenMediaVault, create or edit the stack in **Services → Compose → Files**. On other Docker hosts, copy the file to a private directory. The Compose file pulls `ghcr.io/craigmpeters/octopus-mcp:latest` (linux/amd64), so you do not need the source code or a local build.

The GitHub Actions workflow builds the image on pull requests and publishes it on pushes to `main`. The image will only exist after the first successful publish. New GitHub Container Registry packages may be private: if it is private, make the package public in GitHub Packages settings, or authenticate on the Docker host with `docker login ghcr.io` using a personal access token with `read:packages`. Do not put the token in the Compose file.

1. Edit the `environment` section in your local Compose file and replace the example account number and API key with your own. Octopus provides keys under its account dashboard's Developer settings: https://octopus.energy/help-and-faqs/articles/how-do-i-access-the-octopus-api/ . Keep the configured file private (for example, `chmod 600 compose.yaml`), never commit it to GitHub or paste your key into ChatGPT. Docker administrators can inspect container environment variables.
2. In the OMV Compose **Files** tab, select the stack and click **Pull**, then **Up**. From a Docker terminal, the equivalents are `docker compose pull` and `docker compose up -d`.
3. Check startup in **Services → Compose → Containers → Logs** or with `docker compose logs --tail=30`. With the repository's port mapping, the endpoint is `http://127.0.0.1:8765/mcp` on the Docker host. The port is bound to loopback only.

## 2. Connect securely to ChatGPT

This server deliberately implements **no HTTP authentication**. Keep it on localhost; do not publish it through an unauthenticated Cloudflare tunnel or change the Docker binding to 0.0.0.0. Anyone reaching it can read your account data.

For personal use, OpenAI's Secure MCP Tunnel can carry requests to your private server without opening it to the public. Create an OpenAI tunnel and run its tunnel-client on the same Docker host (or use host networking appropriately) pointing at `http://127.0.0.1:8765/mcp`; follow the current instructions at https://developers.openai.com/api/docs/guides/secure-mcp-tunnels . Tunnel availability, Platform organisation, permissions and account support must be checked during setup. Protect the tunnel credentials. Do not assume a Cloudflare Access login works as ChatGPT MCP OAuth.

In ChatGPT on the web: Plugins > + > Add custom MCP server > Connection: Tunnel, select the tunnel, and configure the connection (the private server itself has no authentication). Create and install the plugin. Then open a new chat and select it with @. See https://developers.openai.com/api/docs/guides/custom-mcp-server . If Secure MCP Tunnel is unavailable to your account, an authenticated OAuth 2.1 gateway is needed before using a public HTTPS endpoint; this project does not implement that gateway. Do not expose this server anonymously.

## 3. Try it

- "List my Octopus meters and tariff agreements."
- "Show my electricity consumption yesterday, including the intervals with the most usage. Flag missing periods."
- "Compare my electricity use this week so far against the same days last week."
- "Find the standard unit rates and standing charge for my tariff for the last week."
- "List products available at 2025-01-01T00:00:00Z, then show the regional variants for a product."
- "Use `tariff_ev_rates` to show the published household and device rates for my four-rate Intelligent Octopus agreement."

`tariff_products` lists published products at a timezone-qualified timestamp; `tariff_product` retrieves the product's regional variants. Publication does not establish eligibility, and these tools do not compare costs. Product data may omit restricted tariffs or eligibility criteria; verify region, meter, payment method and product-specific requirements separately.

`tariff_dual_rates` retrieves day and night rates and standing charges for a dual-register electricity tariff. Verify the meter's register allocation and switching times separately; the rates alone cannot allocate half-hour consumption or establish billed costs.

`tariff_ev_rates` retrieves published household day and night unit rates, EV device peak and off-peak unit rates, and standing charges for four-rate electricity tariffs such as newer Intelligent Octopus Go variants. Use `tariff_product` to find a code under `four_rate_ev_electricity_tariffs`, then request up to 31 inclusive UK calendar dates. The tool returns source URLs, original Octopus VAT values, payment methods, and rate validity dates. Rate validity dates describe the published price period. Daily switching times, account-specific EV dispatches, and the price applied to a particular reading require separate data. Older Intelligent Octopus products can publish time windows under `tariff_rates` instead.

Use the MCP responses as inputs to calculations in ChatGPT or Jupyter. The server provides readings, rates, and their provenance for reuse.

Use the supply-point direction and meter-selection status returned by `list_meters`. If a supply point has multiple meter candidates, the account API does not provide enough physical meter validity data to identify the current one safely. Meter data can be late or incomplete. Data uses London calendar dates, including daylight saving transitions. Consumption responses identify agreements overlapping the requested dates. Electricity consumption is reported in kWh. Gas units are resolved for the selected meter using Kraken GraphQL `consumptionUnits`; SMETS1 data is documented as kWh and SMETS2 as m³. If the unit lookup fails or omits a historical meter, the unit remains explicitly unknown. No gas conversion is applied. Standard tariff rates do not fully model Intelligent Octopus dispatch or other special rates: costs are estimates, not bills. The API does not identify separate car consumption from the household meter. This version does not retrieve EV dispatch slots or real-time usage.

### Check electricity import billing

Use `list_meters` to select an electricity import meter point. Ask `billing` for that `meter_point` and a UK calendar `day` such as `2026-11-08`. If several agreements overlap the day, repeat the call with a returned `agreement_id` for each agreement of interest.

The tool requests consumption charge line items from Kraken with half-hour grouping. Inspect the actual start and end of each record before comparing it with a meter reading. A row can span a longer interval, including a day boundary. The full row amount and quantity apply to that entire period. For additional pages, pass the returned `next_cursor` as `after` with the same meter point, date and agreement ID. An empty page can still have a continuation. An empty result does not establish a zero charge.

Kraken supplies `netAmount`, `numberOfUnits` and `settlementUnit`. Its schema does not specify the currency scale for this amount or identify a final statement in these rows. Confirm the units, tax treatment and statement reconciliation before using a line to infer a billed unit rate.

## Estimate export credit

1. Use `list_meters` to find the electricity export supply point, then call `consumption` for its meter and the desired UK dates. Check `coverage` before calculating a total. Keep any import readings separate.
2. Use `applicable_agreements` to identify the export tariff code for each part of the window. For a code like `E-1R-EXAMPLE-A`, use `EXAMPLE` as the candidate product code. Confirm the exact tariff code in the product's regional variants with `tariff_product`, then call `tariff_rates` with `fuel: electricity` and the same date window. The response includes the upstream endpoints, UTC period, units, and empty rate categories.
3. In your client, match each full UTC reading interval to its export agreement and one published unit-rate row. Treat `valid_to` as exclusive and a null bound as open-ended. If several rate rows match, use the applicable payment method when it is known. A null payment method is unspecified. Report any missing or unresolved intervals separately.
4. Multiply exported kWh by the matched pence-per-kWh rate and divide the sum by 100 to estimate the credit in pounds. Use the published VAT field appropriate to the estimate and check statement treatment with Octopus. Standing charges are separate daily amounts. Exported kWh measures energy sent to the grid. Solar generation and self-consumption require separate telemetry.

## Deploy and refresh new MCP tools

When a release adds or changes tools, update the running server, then refresh the tool list in ChatGPT.

1. After the PR is merged, wait for **Build and publish container** to succeed on `main` in GitHub Actions. The workflow builds on pull requests and publishes on pushes to `main`. Each published image has a `latest` tag and a tag for its Git commit. If your OMV stack uses a pinned tag, edit its `image:` line to use the new commit tag before pulling.
2. In **OMV → Services → Compose → Files**, select the Octopus MCP stack. Click **Pull**, then **Up**. Compose recreates the container when the image changes, so there is no need to take the stack down first.
3. In **ChatGPT on the web → Plugins**, open the existing Octopus Energy connection and click **Refresh** to load its updated tool list. [OpenAI's refresh instructions](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt#refresh-metadata)
4. Start a new conversation, select Octopus Energy with `@`, and ask it to call a newly added tool. For tariff discovery, try “Use `tariff_products` to list products available at `2026-11-17T00:00:00Z`.” A successful call to an older tool confirms connectivity only.

If a new tool is missing, open **OMV → Services → Compose → Containers**, select the `octopusmcp` container, and click **Inspect**. Compare its top-level `Image` field to the `Id` shown under **Services → Compose → Images → Inspect** for the repository and tag you just pulled. The registry manifest digest and the Docker image ID are different identifiers. Share only the `Image` field if you need help, since the full container Inspect output can contain credentials.

If the image ID matches, use **Logs** on that same container while making a read-only request from ChatGPT. For example, request standard rates for public tariff `E-1R-AGILE-24-10-01-A` on a specific date, then look for the matching tariff code and date near the bottom of the logs. A matching request confirms the tunnel reaches that container. If the new tool still does not appear, check the ChatGPT connection's refresh and the tool list in a new conversation. If the request is missing from the container's logs, check the tunnel target and its `/mcp` path.

## Container publishing

The workflow also tags each published image with its Git commit SHA. For reproducible deployments, replace `latest` in `compose.yaml` with the desired commit SHA. Publishing uses the repository's `GITHUB_TOKEN` and `packages: write` permission; check the Actions run if publishing fails. The image is currently built for linux/amd64, suitable for the Dell PowerEdge R230.

## Status

After the Phase 2 deployment on OpenMediaVault and a ChatGPT connection refresh, all three discovery tools passed a live test through the Secure MCP Tunnel. The checks covered the published product list, regional tariff variants, and day and night rates and standing charges for a sample dual-register tariff. If a tool fails, share the error with account identifiers and secrets removed. To revoke a leaked key, use your Octopus developer settings.
