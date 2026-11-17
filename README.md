# Personal Octopus Energy MCP — first version

A personal, read-only MCP server: list meters and tariff agreements, fetch electricity/gas consumption, and fetch standard unit rates and standing charges. It does not control charging or change account settings. Data is fetched directly from Octopus; no database or account data is deliberately stored by this app. ChatGPT may retain tool results according to your settings.

## 1. Set up on your Docker host

Unzip this directory on the machine running Docker, then open a terminal in the directory. You will need Docker Compose and internet access to Octopus. On OpenMediaVault you can use its Compose tooling with this directory as the build context.

1. Copy `.env.example` to `.env`: `cp .env.example .env`.
2. Set your account number and API key in `.env` using a local editor. Octopus provides keys under its account dashboard's Developer settings: https://octopus.energy/help-and-faqs/articles/how-do-i-access-the-octopus-api/ . Do not paste the key into ChatGPT. Restrict access: `chmod 600 .env`.
3. Run `docker compose up -d --build`.
4. `docker compose logs --tail=30` should show startup. The endpoint is `http://127.0.0.1:8765/mcp` on that host. The port is bound to loopback only.

## 2. Connect securely to ChatGPT

This server deliberately implements **no HTTP authentication**. Keep it on localhost; do not publish it through an unauthenticated Cloudflare tunnel or change the Docker binding to 0.0.0.0. Anyone reaching it can read your account data.

For personal use, OpenAI's Secure MCP Tunnel can carry requests to your private server without opening it to the public. Create an OpenAI tunnel and run its tunnel-client on the same Docker host (or use host networking appropriately) pointing at `http://127.0.0.1:8765/mcp`; follow the current instructions at https://developers.openai.com/api/docs/guides/secure-mcp-tunnels . Tunnel availability, Platform organisation, permissions and account support must be checked during setup. Protect the tunnel credentials. Do not assume a Cloudflare Access login works as ChatGPT MCP OAuth.

In ChatGPT on the web: Plugins > + > Add custom MCP server > Connection: Tunnel, select the tunnel, and configure the connection (the private server itself has no authentication). Create and install the plugin. Then open a new chat and select it with @. See https://developers.openai.com/api/docs/guides/custom-mcp-server . If Secure MCP Tunnel is unavailable to your account, an authenticated OAuth 2.1 gateway is needed before using a public HTTPS endpoint; this project does not implement that gateway. Do not expose this server anonymously.

## 3. Try it

- "List my Octopus meters and tariff agreements."
- "Show my electricity consumption yesterday, including the intervals with the most usage. Flag missing periods."
- "Compare my electricity use this week so far against the same days last week."
- "Find the standard unit rates and standing charge for my tariff for the last week."

Choose the current import meter, not an old or export meter. Meter data can be late or incomplete. Data uses London calendar dates, including daylight saving transitions. Gas readings may be in m³ rather than kWh. Standard tariff rates do not fully model Intelligent Octopus dispatch or other special rates: costs are estimates, not bills. The API does not identify separate car consumption from the household meter. This version does not retrieve EV dispatch slots or real-time usage.

## Status

The code was checked locally using mocked API responses; it has not been tested with your Octopus account, Docker installation, or a ChatGPT tunnel. Account response shapes and API behaviour can vary; if a tool fails, share the error with account identifiers and secrets removed. To stop: `docker compose down`. To revoke a leaked key use your Octopus developer settings.
