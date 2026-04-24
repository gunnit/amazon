#!/usr/bin/env node
// Stdio MCP test harness for Inthezon MCP.
// Spawns the MCP, drives each tool with sensible inputs, reports pass/fail.

import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const MCP_PATH = "/Users/giuseppepretto/Projects/amazon/mcp-server/packages/mcp-cli/dist/index.js";
const NODE = "/opt/homebrew/opt/node@22/bin/node";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
const CAMP_ID = "22222222-2222-2222-2222-222222222222";
const FORECAST_ID = "33333333-3333-3333-3333-333333333333";
const RULE_ID = "44444444-4444-4444-4444-444444444444";
const ASIN = "B0SEED0001";
const TODAY = new Date().toISOString().slice(0, 10);
const D30 = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);
const D60 = new Date(Date.now() - 60 * 86400_000).toISOString().slice(0, 10);
const D90 = new Date(Date.now() - 90 * 86400_000).toISOString().slice(0, 10);

// Tool plan: name -> args (or null to skip / "destructive" to mark)
const PLAN = [
  // session
  { name: "whoami" },
  { name: "backend_health" },
  // accounts
  { name: "list_accounts" },
  { name: "get_accounts_summary" },
  { name: "get_account", args: { account_id: ACCOUNT_ID } },
  { name: "get_account_status", args: { account_id: ACCOUNT_ID } },
  // raw data
  { name: "query_sales", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, limit: 5 } },
  { name: "query_sales_aggregated", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, group_by: "day" } },
  { name: "query_orders", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, limit: 5 } },
  { name: "get_inventory", args: { account_ids: [ACCOUNT_ID] } },
  { name: "get_inventory", args: { account_ids: [ACCOUNT_ID], low_stock_only: true } },
  { name: "get_advertising_metrics", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  // catalog
  { name: "list_products", args: { account_ids: [ACCOUNT_ID] } },
  { name: "get_product", args: { asin: ASIN } },
  { name: "list_product_images", args: { account_id: ACCOUNT_ID, asin: ASIN } },
  // analytics
  { name: "get_dashboard_kpis", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_trends", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY, metrics: ["revenue", "units"] } },
  { name: "get_top_performers", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_period_comparison", args: { account_ids: [ACCOUNT_ID], period1_start: D60, period1_end: D30, period2_start: D30, period2_end: TODAY } },
  { name: "get_product_trends", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_sales_by_category", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_orders_by_hour", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_advertising_insights", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_returns_analytics", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  { name: "get_ads_vs_organic", args: { account_ids: [ACCOUNT_ID], start_date: D30, end_date: TODAY } },
  // forecasts
  { name: "list_forecasts", args: { account_ids: [ACCOUNT_ID] } },
  { name: "get_forecast", args: { forecast_id: FORECAST_ID } },
  { name: "list_forecastable_products", args: { account_id: ACCOUNT_ID } },
  // alerts
  { name: "list_alert_rules" },
  { name: "get_alert_summary" },
  { name: "list_alerts", args: { status: "unread" } },
  // scheduled reports
  { name: "list_scheduled_reports" },
  // market research
  { name: "list_market_research" },
  // recommendations
  { name: "list_recommendations" },
  // composite
  { name: "snapshot", args: { start_date: D30, end_date: TODAY } },
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
        if (pending.has(id)) {
          pending.delete(id);
          reject(new Error(`timeout: ${method}`));
        }
      }, 30000);
    });
  }

  function notify(method, params) {
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n");
  }

  // initialize
  await send("initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "harness", version: "0" },
  });
  notify("notifications/initialized");

  // verify list
  const list = await send("tools/list", {});
  const toolNames = new Set((list.result?.tools || []).map((t) => t.name));
  console.log(`# MCP exposes ${toolNames.size} tools`);

  const results = [];
  for (const step of PLAN) {
    if (!toolNames.has(step.name)) {
      results.push({ name: step.name, status: "MISSING" });
      continue;
    }
    try {
      const resp = await send("tools/call", { name: step.name, arguments: step.args || {} });
      if (resp.error) {
        results.push({ name: step.name, status: "ERROR", detail: resp.error.message });
      } else {
        const isError = resp.result?.isError;
        const text = resp.result?.content?.[0]?.text || "";
        if (isError) {
          results.push({ name: step.name, status: "TOOL_ERR", detail: text.slice(0, 240) });
        } else {
          results.push({ name: step.name, status: "OK", preview: text.slice(0, 160) });
        }
      }
    } catch (e) {
      results.push({ name: step.name, status: "EXC", detail: String(e).slice(0, 240) });
    }
  }

  console.log("\n# Results");
  let ok = 0, fail = 0;
  for (const r of results) {
    const tag = r.status === "OK" ? "✅" : "❌";
    if (r.status === "OK") ok++; else fail++;
    console.log(`${tag} ${r.name.padEnd(36)} ${r.status}${r.detail ? "  " + r.detail : ""}`);
  }
  console.log(`\n# Summary: ${ok} ok, ${fail} fail / ${results.length} total`);

  if (stderr.trim()) {
    console.log("\n# stderr (last 800 chars):");
    console.log(stderr.slice(-800));
  }

  child.kill();
  process.exit(fail ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
