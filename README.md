# Personal Octopus Energy MCP — first version

A personal, read-only MCP server: list meters and tariff agreements, fetch electricity/gas consumption, and fetch standard unit rates and standing charges. It does not control charging or change account settings. Data is fetched directly from Octopus; no database or account data is deliberately stored by this app. ChatGPT may retain tool results according to your settings.

## 1. Set up on your Docker host

Copy `compose.yaml` from this repository to a private directory on your Docker host, then open a terminal there. The Compose file pulls `ghcr.io/craigmpeters/octopus-mcp:latest` (linux/amd64), so you do not need the source code or a local build. On OpenMediaVault, use the Compose plugin and enter the account settings directly in its Compose configuration.

The GitHub Actions workflow builds the image on pull requests and publishes it on pushes to `main`. The image will only exist after the first successful publish. New GitHub Container Registry packages may be private: if it is private, make the package public in GitHub Packages settings, or authenticate on the Docker host with `docker login ghcr.io` using a personal access token with `read:packages`. Do not put the token in the Compose file.

1. Edit the `environment` section in your local Compose file and replace the example account number and API key with your own. Octopus provides keys under its account dashboard's Developer settings: https://octopus.energy/help-and-faqs/articles/how-do-i-access-the-octopus-api/ . Keep the configured file private (for example, `chmod 600 compose.yaml`), never commit it to GitHub or paste your key into ChatGPT. Docker administrators can inspect container environment variables.
2. Run `docker compose pull` followed by `docker compose up -d`. To update later, run the same two commands.
3. `docker compose logs --tail=30` should show startup. The endpoint is `http://127.0.0.1:8765/mcp` on that host. The port is bound to loopback only.

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

`tariff_products` lists published products at a timezone-qualified timestamp; `tariff_product` retrieves the product's regional variants. Publication does not establish eligibility, and these tools do not compare costs. Product data may omit restricted tariffs or eligibility criteria; verify region, meter, payment method and product-specific requirements separately.

`tariff_dual_rates` retrieves day and night rates and standing charges for a dual-register electricity tariff. Verify the meter's register allocation and switching times separately; the rates alone cannot allocate half-hour consumption or establish billed costs.

Use the supply-point direction and meter-selection status returned by `list_meters`. If a supply point has multiple meter candidates, the account API does not provide enough physical meter validity data to identify the current one safely. Meter data can be late or incomplete. Data uses London calendar dates, including daylight saving transitions. Consumption responses identify agreements overlapping the requested dates. Electricity consumption is reported in kWh. Gas units are resolved for the selected meter using Kraken GraphQL `consumptionUnits`; SMETS1 data is documented as kWh and SMETS2 as m³. If the unit lookup fails or omits a historical meter, the unit remains explicitly unknown. No gas conversion is applied. Standard tariff rates do not fully model Intelligent Octopus dispatch or other special rates: costs are estimates, not bills. The API does not identify separate car consumption from the household meter. This version does not retrieve EV dispatch slots or real-time usage.

## Container publishing

The workflow also tags each published image with its Git commit SHA. For reproducible deployments, replace `latest` in `compose.yaml` with the desired commit SHA. Publishing uses the repository's `GITHUB_TOKEN` and `packages: write` permission; check the Actions run if publishing fails. The image is currently built for linux/amd64, suitable for the Dell PowerEdge R230.

## Status

The code was checked locally using mocked API responses; it has not been tested with your Octopus account, Docker installation, or a ChatGPT tunnel. Account response shapes and API behaviour can vary; if a tool fails, share the error with account identifiers and secrets removed. To stop: `docker compose down`. To revoke a leaked key use your Octopus developer settings.
