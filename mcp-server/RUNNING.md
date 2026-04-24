# Running the Inthezon MCP locally

This guide covers the **Node/TypeScript** MCP under `packages/`. The legacy
Python implementation (`server.py`, `cli.py`, `db.py`) still works against a
direct Postgres connection but is no longer the recommended path.

## Prerequisites

- **Node ≥ 22** (Node 25 from Homebrew currently has a broken `simdjson` link;
  `node@22` is the safe choice).
- A reachable Inthezon backend (`http://localhost:8000` by default).
- An Inthezon account (`email` + `password`) with at least one Amazon account
  connected via the web app or `inthezon connect-account`.

## One-time setup

```bash
cd mcp-server

# Use Node 22 explicitly if Homebrew Node 25 is broken
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"

npm install
npm run build
```

This builds three workspaces: `@inthezon/shared-sdk`, `@inthezon/mcp-server`,
`@inthezon/mcp-cli`.

## Authentication

```bash
node packages/mcp-cli/dist/index.js login
```

Prompts for:
- Backend URL (default `http://localhost:8000`, override with
  `INTHEZON_API_URL`).
- Email + password.

Credentials live in `~/.inthezon/mcp-cli.json` (mode `0600`). Override the
config path with `INTHEZON_CONFIG_PATH`.

Useful commands:
- `inthezon status` — backend health + current session + accounts count.
- `inthezon doctor` — quick diagnostics.
- `inthezon accounts` — list connected Amazon accounts.
- `inthezon select-accounts` — interactively pick the default accounts MCP tools
  will use when no `account_ids` is passed. Empty selection clears the default.
- `inthezon exports-dir [path]` — change where binary exports are saved
  (default `~/.inthezon/exports/`, override with `INTHEZON_EXPORTS_DIR`).
- `inthezon export` — interactive flow for CSV/Excel/PowerPoint/forecast/PDF
  exports; the resulting file is saved to the exports dir.
- `inthezon logout` — clears tokens and selection (keeps backend URL +
  exports dir).

## Wiring the MCP into Claude Code / Codex

```json
{
  "mcpServers": {
    "inthezon": {
      "command": "node",
      "args": [
        "/absolute/path/to/mcp-server/packages/mcp-cli/dist/index.js",
        "mcp",
        "start"
      ]
    }
  }
}
```

If you `npm link` the CLI globally, you can simplify to:

```json
{
  "mcpServers": {
    "inthezon": {
      "command": "inthezon",
      "args": ["mcp", "start"]
    }
  }
}
```

`inthezon mcp config` prints the snippet on demand.

## Smoke testing without an MCP client

Pipe a manual `initialize` + `tools/list` over stdio:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | node packages/mcp-cli/dist/index.js mcp start
```

You should get back the server info and a `tools` array with ~70 entries.

## Tool catalog (high level)

See `~/.claude/skills/inthezon-mcp/SKILL.md` for the full assistant-facing
catalog. Tools cover:

- session/context (`whoami`, `backend_health`, `set_selected_accounts`)
- accounts (list/get/create/update/delete/sync/test)
- raw data (`query_sales`, `query_orders`, `get_inventory`,
  `get_advertising_metrics`)
- catalog (products, prices, availability, images)
- analytics (dashboard KPIs, trends, comparisons, returns, ads-vs-organic,
  product trends, category breakdown, hourly orders, advertising insights)
- forecasts (list/get/generate, forecastable products)
- alerts (rules CRUD + alerts list + read/unread)
- scheduled reports (list, run-now, download)
- market research (generate, refresh, matrix, search, suggest competitors)
- strategic recommendations (list, generate, update status)
- exports (CSV/Excel/PPTX/PDF/forecast package — saved to local exports dir)
- composite (`snapshot`)

## Files & layout

```
mcp-server/
├── packages/
│   ├── shared-sdk/         # HTTP client + local config store
│   ├── mcp-server/         # MCP tool definitions
│   └── mcp-cli/            # `inthezon` CLI entry point
├── server.py, cli.py, ...  # Legacy Python implementation (kept for reference)
├── README.md               # Original product README
└── RUNNING.md              # This file
```

## Known limitations

- Multipart uploads (catalog `bulk-update` / product images upload) are not
  exposed as MCP tools — use the web app.
- Google Sheets connection requires browser OAuth; not exposed via MCP.
- Long-running operations (forecast generation, market research, scheduled
  report runs) return immediately and must be polled.
- Permission checks (e.g. `analytics/admin/data-health` requires superuser)
  surface as 403 from the backend.
