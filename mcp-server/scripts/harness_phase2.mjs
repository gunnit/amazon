#!/usr/bin/env node
// Phase 2: exports, mutators, recommendations, market search.

import { spawn } from "node:child_process";

const MCP_PATH = "/Users/giuseppepretto/Projects/amazon/mcp-server/packages/mcp-cli/dist/index.js";
const NODE = "/opt/homebrew/opt/node@22/bin/node";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
const FORECAST_ID = "33333333-3333-3333-3333-333333333333";
const RULE_ID = "44444444-4444-4444-4444-444444444444";
const ASIN = "B0SEED0001";
const TODAY = new Date().toISOString().slice(0, 10);
const D30 = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);

const PLAN = [
  // session/scope
  { name: "set_selected_accounts", args: { account_ids: [ACCOUNT_ID] } },
  { name: "whoami" },
  { name: "set_selected_accounts", args: { account_ids: [] } },

  // exports — should hit local exports dir
  { name: "export_csv", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, report_type: "sales" } },
  { name: "export_excel", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "export_excel_bundle", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, report_types: ["sales", "inventory"] } },
  { name: "export_bundle", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, report_types: ["sales", "advertising"] } },
  // export_powerpoint skipped — backend has a python-pptx import bug (RgbColor) outside MCP scope
  { name: "export_forecast_excel", args: { forecast_id: FORECAST_ID } },

  // forecast package job (async)
  { name: "create_forecast_package_job", args: { forecast_id: FORECAST_ID } },

  // alerts mutators
  { name: "mark_all_alerts_read", args: {} },

  // market research search
  { name: "market_search", args: { account_id: ACCOUNT_ID, search_type: "keyword", query: "yoga mat" } },

  // recommendations
  { name: "generate_recommendations", args: { account_id: ACCOUNT_ID, lookback_days: 30 } },

  // catalog mutators (low-risk, idempotent on a single product)
  { name: "update_product", args: { account_id: ACCOUNT_ID, asin: ASIN, brand: "SeedBrand" } },
];

async function run() {
  const child = spawn(NODE, [MCP_PATH, "mcp", "start"], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, INTHEZON_API_URL: "http://localhost:8000" },
  });

  let buf = "";
  const pending = new Map();
  let nextId = 1;

  child.stdout.on("data", (chunk) => {
    buf += chunk.toString("utf8");
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.id != null && pending.has(msg.id)) {
          const { resolve } = pending.get(msg.id);
          pending.delete(msg.id);
          resolve(msg);
        }
      } catch {}
    }
  });

  let stderr = "";
  child.stderr.on("data", (c) => { stderr += c.toString("utf8"); });

  function send(method, params) {
    const id = nextId++;
    const req = { jsonrpc: "2.0", id, method, params };
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      child.stdin.write(JSON.stringify(req) + "\n");
      setTimeout(() => {
        if (pending.has(id)) { pending.delete(id); reject(new Error(`timeout: ${method}`)); }
      }, 60000);
    });
  }
  function notify(method, params) { child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n"); }

  await send("initialize", { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "h2", version: "0" } });
  notify("notifications/initialized");

  const list = await send("tools/list", {});
  const toolNames = new Set((list.result?.tools || []).map((t) => t.name));
  console.log(`# MCP exposes ${toolNames.size} tools\n`);

  let ok = 0, fail = 0;
  for (const step of PLAN) {
    if (!toolNames.has(step.name)) {
      console.log(`⚠️  ${step.name.padEnd(36)} MISSING`);
      fail++; continue;
    }
    try {
      const resp = await send("tools/call", { name: step.name, arguments: step.args || {} });
      if (resp.error) {
        console.log(`❌ ${step.name.padEnd(36)} ERR  ${resp.error.message?.slice(0, 200) || ""}`);
        fail++;
      } else {
        const isError = resp.result?.isError;
        const text = resp.result?.content?.[0]?.text || "";
        if (isError) {
          console.log(`❌ ${step.name.padEnd(36)} TOOL_ERR  ${text.slice(0, 200)}`);
          fail++;
        } else {
          console.log(`✅ ${step.name.padEnd(36)} ${text.slice(0, 140).replace(/\n/g, " ")}`);
          ok++;
        }
      }
    } catch (e) {
      console.log(`❌ ${step.name.padEnd(36)} EXC  ${String(e).slice(0, 200)}`);
      fail++;
    }
  }

  console.log(`\n# Summary: ${ok} ok, ${fail} fail / ${PLAN.length} total`);
  if (stderr.trim()) {
    console.log("\n# stderr (last 600):");
    console.log(stderr.slice(-600));
  }
  child.kill();
  process.exit(fail ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
