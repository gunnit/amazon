#!/usr/bin/env node
// Phase 3: alert rules, market research, scheduled reports, recommendations,
// and remaining catalog/forecast/recommendation tools.

import { spawn } from "node:child_process";

const MCP_PATH = "/Users/giuseppepretto/Projects/amazon/mcp-server/packages/mcp-cli/dist/index.js";
const NODE = "/opt/homebrew/opt/node@22/bin/node";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
const ASIN = "B0SEED0001";
const ASIN2 = "B0SEED0002";
const FORECAST_ID = "33333333-3333-3333-3333-333333333333";

const PLAN = [
  // alert rules — create / update / mark / delete (full CRUD on a synthetic rule)
  { name: "create_alert_rule", args: {
      name: "Harness rule",
      alert_type: "low_stock",
      conditions: { threshold: 5 },
      notification_channels: ["email"],
      is_enabled: true,
  }},
  { name: "list_alert_rules" },
  // market research
  { name: "suggest_competitors", args: { category: "Electronics" } },
  // forecasts
  { name: "get_product_forecast", args: { asin: ASIN } },
  // catalog mutators
  { name: "bulk_update_prices", args: {
      account_id: ACCOUNT_ID,
      updates: [{ asin: ASIN, price: 41.50 }],
  }},
  { name: "update_product_availability", args: {
      account_id: ACCOUNT_ID,
      asin: ASIN,
      is_available: true,
  }},
  // recommendations - get one + update its status
  { name: "list_recommendations", args: { limit: 1 } },
  // sync
  { name: "trigger_account_sync", args: { account_id: ACCOUNT_ID } },
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

  await send("initialize", { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "h3", version: "0" } });
  notify("notifications/initialized");
  await send("tools/list", {});

  const created = {};
  let ok = 0, fail = 0;
  for (const step of PLAN) {
    try {
      const resp = await send("tools/call", { name: step.name, arguments: step.args || {} });
      const isError = resp.result?.isError;
      const text = resp.result?.content?.[0]?.text || "";
      if (resp.error || isError) {
        console.log(`❌ ${step.name.padEnd(36)} ${(resp.error?.message || text).slice(0, 200)}`);
        fail++;
      } else {
        console.log(`✅ ${step.name.padEnd(36)} ${text.slice(0, 130).replace(/\n/g, " ")}`);
        ok++;
        // capture an id if present
        try {
          const obj = JSON.parse(text);
          if (step.name === "create_alert_rule" && obj.id) created.ruleId = obj.id;
          if (step.name === "list_recommendations" && Array.isArray(obj.recommendations) && obj.recommendations[0])
            created.recId = obj.recommendations[0].id;
        } catch {}
      }
    } catch (e) {
      console.log(`❌ ${step.name.padEnd(36)} EXC ${String(e).slice(0, 200)}`);
      fail++;
    }
  }

  // Follow-ups using captured ids
  const followups = [];
  if (created.ruleId) {
    followups.push({ name: "update_alert_rule", args: { rule_id: created.ruleId, is_enabled: false } });
    followups.push({ name: "delete_alert_rule", args: { rule_id: created.ruleId } });
  }
  if (created.recId) {
    followups.push({ name: "get_recommendation", args: { rec_id: created.recId } });
    followups.push({ name: "update_recommendation_status", args: { rec_id: created.recId, status: "dismissed", outcome_notes: "harness test" } });
  }

  for (const step of followups) {
    try {
      const resp = await send("tools/call", { name: step.name, arguments: step.args });
      const isError = resp.result?.isError;
      const text = resp.result?.content?.[0]?.text || "";
      if (resp.error || isError) {
        console.log(`❌ ${step.name.padEnd(36)} ${(resp.error?.message || text).slice(0, 200)}`);
        fail++;
      } else {
        console.log(`✅ ${step.name.padEnd(36)} ${text.slice(0, 130).replace(/\n/g, " ")}`);
        ok++;
      }
    } catch (e) {
      console.log(`❌ ${step.name.padEnd(36)} EXC ${String(e).slice(0, 200)}`);
      fail++;
    }
  }

  console.log(`\n# Summary: ${ok} ok, ${fail} fail / ${ok + fail} total`);
  if (stderr.trim()) console.log("\n# stderr (last 400):\n" + stderr.slice(-400));
  child.kill();
  process.exit(fail ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(2); });
