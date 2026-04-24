# MCP test scripts

Tooling used to validate the Inthezon MCP end-to-end against the local Docker
stack. Everything here is self-contained and safe to re-run.

## Files

- `seed_test_data.sql` — idempotent seed for the `mcp-tester@example.com` org
  (UUID `5be2ce2e-ecdb-4a4c-80ad-488382e1403f`). Inserts:
  - 1 Amazon account (UUID `1111…1111`, IT marketplace, sync_status `SUCCESS`)
  - 5 products `B0SEED0001`–`B0SEED0005`
  - 30 days of `sales_data` per ASIN
  - Latest `inventory_data` snapshot (ASIN `B0SEED0002` at 3 units to trigger
    low-stock paths)
  - 1 advertising campaign + 14 days of metrics
  - 1 forecast (UUID `3333…3333`, sales, 30-day horizon)
  - 1 alert rule + 1 triggered alert
- `harness_phase1.mjs` — drives the 35 read-mostly tools (session, accounts,
  raw data, catalog reads, analytics, forecasts, alerts, reports lists,
  market research lists, recommendations lists, snapshot).
- `harness_phase2.mjs` — exports (CSV / Excel / Excel bundle / Bundle ZIP /
  forecast Excel), forecast-package job, mutators (set_selected_accounts,
  mark_all_alerts_read, update_product), market_search,
  generate_recommendations.
- `harness_phase3.mjs` — alert-rule CRUD round-trip, suggest_competitors,
  per-ASIN forecast lookup, bulk_update_prices, update_product_availability,
  trigger_account_sync, recommendation update.

## Prerequisites

1. Docker stack running (`docker-compose up -d`).
2. MCP CLI logged in as a user in the seeded org:
   ```bash
   node packages/mcp-cli/dist/index.js login
   ```
3. Node 22 in PATH (`/opt/homebrew/opt/node@22/bin` on this machine — Node 25
   from Homebrew is currently broken).

## Running

```bash
# Seed (or re-seed) the synthetic data
docker exec -i amazon-postgres-1 psql -U postgres -d inthezon \
  < mcp-server/scripts/seed_test_data.sql

# Drive the harnesses
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
node mcp-server/scripts/harness_phase1.mjs
node mcp-server/scripts/harness_phase2.mjs
node mcp-server/scripts/harness_phase3.mjs
```

## Known non-MCP failures

These tools surface backend / SP-API / data limitations and are NOT MCP layer
bugs:

| Tool | Reason |
| --- | --- |
| `list_product_images`, `bulk_update_prices`, `update_product_availability`, `test_account_connection` | Need real SP-API Seller ID. Synthetic account has none. |
| `export_powerpoint` | Backend `python-pptx` import bug (`RgbColor` not exported in current pptx version). |
| `get_product_forecast` for a seed ASIN | Seeded forecast is account-wide (`asin = NULL`), so per-ASIN lookup returns 404 by design. |

All other 70+ tools pass against the seeded org.
