import { writeFileSync } from "node:fs";
import { join } from "node:path";

import {
  BackendClient,
  ensureExportsDir,
  loadLocalState,
  saveLocalState,
  setSelectedAccounts,
  type BinaryDownload,
} from "@inthezon/shared-sdk";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

function jsonContent(data: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(data, null, 2),
      },
    ],
  };
}

function textContent(text: string) {
  return {
    content: [{ type: "text" as const, text }],
  };
}

function createClient() {
  const state = loadLocalState();
  if (!state.accessToken || !state.refreshToken) {
    throw new Error("No active session found. Run `inthezon login` first.");
  }

  return new BackendClient({
    backendUrl: state.backendUrl,
    accessToken: state.accessToken,
    refreshToken: state.refreshToken,
    onSessionUpdate(tokens) {
      saveLocalState({
        ...loadLocalState(),
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
    },
  });
}

function resolveAccountIds(accountIds: string[] | undefined): string[] | undefined {
  if (accountIds && accountIds.length > 0) return accountIds;
  const state = loadLocalState();
  return state.selectedAccountIds && state.selectedAccountIds.length > 0
    ? state.selectedAccountIds
    : undefined;
}

function saveBinary(download: BinaryDownload, customName?: string): string {
  const dir = ensureExportsDir();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const base = customName || download.filename || "export.bin";
  const filename = `${stamp}_${base}`;
  const fullPath = join(dir, filename);
  writeFileSync(fullPath, download.bytes);
  return fullPath;
}

const dateString = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD");
const uuidString = z.string().uuid();

export function registerInthezonTools(server: McpServer): void {
  // ===========================================================================
  // Session / context
  // ===========================================================================

  server.registerTool(
    "whoami",
    {
      description: "Return the currently authenticated user, organization and backend URL.",
      inputSchema: {},
    },
    async () => {
      const state = loadLocalState();
      const client = createClient();
      const [user, organization] = await Promise.all([
        client.getMe(),
        client.getOrganization(),
      ]);
      return jsonContent({
        backend_url: state.backendUrl,
        user,
        organization,
        selected_account_ids: state.selectedAccountIds || [],
        exports_dir: ensureExportsDir(state),
      });
    },
  );

  server.registerTool(
    "backend_health",
    {
      description: "Check the Inthezon backend health endpoint.",
      inputSchema: {},
    },
    async () => {
      const client = createClient();
      return jsonContent(await client.health());
    },
  );

  server.registerTool(
    "set_selected_accounts",
    {
      description:
        "Persist a default set of Amazon account UUIDs that other tools will use when no `account_ids` is passed. Pass an empty array to clear.",
      inputSchema: {
        account_ids: z.array(uuidString).describe("Amazon account UUIDs."),
      },
    },
    async ({ account_ids }) => {
      const state = setSelectedAccounts(account_ids);
      return jsonContent({ selected_account_ids: state.selectedAccountIds || [] });
    },
  );

  // ===========================================================================
  // Accounts
  // ===========================================================================

  server.registerTool(
    "list_accounts",
    {
      description: "List connected Amazon accounts for the authenticated Inthezon organization.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().listAccounts()),
  );

  server.registerTool(
    "get_accounts_summary",
    {
      description: "Return aggregate account counts (total/active/syncing/error) plus per-account status.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().getAccountsSummary()),
  );

  server.registerTool(
    "get_account",
    {
      description: "Get a single Amazon account by UUID.",
      inputSchema: { account_id: uuidString },
    },
    async ({ account_id }) => jsonContent(await createClient().getAccount(account_id)),
  );

  server.registerTool(
    "get_account_status",
    {
      description: "Get sync status (with sales/units/asin counts) for a single Amazon account.",
      inputSchema: { account_id: uuidString },
    },
    async ({ account_id }) => jsonContent(await createClient().getAccountStatus(account_id)),
  );

  server.registerTool(
    "test_account_connection",
    {
      description: "Run a SP-API smoke test on the given account and return the result.",
      inputSchema: { account_id: uuidString },
    },
    async ({ account_id }) => jsonContent(await createClient().testAccountConnection(account_id)),
  );

  server.registerTool(
    "trigger_account_sync",
    {
      description: "Trigger a full sync for one Amazon account.",
      inputSchema: { account_id: uuidString },
    },
    async ({ account_id }) => jsonContent(await createClient().triggerAccountSync(account_id)),
  );

  server.registerTool(
    "sync_all_accounts",
    {
      description: "Trigger a sync for every active account in the organization.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().syncAllAccounts()),
  );

  server.registerTool(
    "update_account",
    {
      description: "Update mutable fields on an Amazon account (name, active flag, credentials).",
      inputSchema: {
        account_id: uuidString,
        account_name: z.string().optional(),
        is_active: z.boolean().optional(),
        advertising_profile_id: z.string().optional(),
      },
    },
    async ({ account_id, ...rest }) => jsonContent(await createClient().updateAccount(account_id, rest)),
  );

  server.registerTool(
    "delete_account",
    {
      description: "Delete an Amazon account from the organization. Irreversible.",
      inputSchema: { account_id: uuidString },
    },
    async ({ account_id }) => {
      await createClient().deleteAccount(account_id);
      return jsonContent({ status: "deleted", account_id });
    },
  );

  // ===========================================================================
  // Sales / orders / inventory / advertising raw data
  // ===========================================================================

  server.registerTool(
    "query_sales",
    {
      description: "Query raw sales rows for a date range, optionally filtered by account or ASIN.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        asins: z.array(z.string()).optional(),
        limit: z.number().int().min(1).max(10000).default(1000),
        offset: z.number().int().min(0).default(0),
      },
    },
    async ({ start_date, end_date, account_ids, asins, limit, offset }) => jsonContent(
      await createClient().getSales({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        asins,
        limit,
        offset,
      }),
    ),
  );

  server.registerTool(
    "query_sales_aggregated",
    {
      description: "Aggregate sales by day, week or month.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        group_by: z.enum(["day", "week", "month"]).default("day"),
        account_ids: z.array(uuidString).optional(),
      },
    },
    async ({ start_date, end_date, group_by, account_ids }) => jsonContent(
      await createClient().getSalesAggregated({
        startDate: start_date,
        endDate: end_date,
        groupBy: group_by,
        accountIds: resolveAccountIds(account_ids),
      }),
    ),
  );

  server.registerTool(
    "query_orders",
    {
      description: "Query the orders table with optional account/status/ASIN filters.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_id: uuidString.optional(),
        order_status: z.string().optional(),
        asin: z.string().optional(),
        limit: z.number().int().min(1).max(500).default(50),
        offset: z.number().int().min(0).default(0),
      },
    },
    async ({ start_date, end_date, account_id, order_status, asin, limit, offset }) => jsonContent(
      await createClient().getOrders({
        startDate: start_date,
        endDate: end_date,
        accountId: account_id,
        orderStatus: order_status,
        asin,
        limit,
        offset,
      }),
    ),
  );

  server.registerTool(
    "get_inventory",
    {
      description: "Get inventory snapshot data, optionally filtered by account/ASIN, low-stock only, or date range.",
      inputSchema: {
        snapshot_date: dateString.optional(),
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        asins: z.array(z.string()).optional(),
        low_stock_only: z.boolean().default(false),
        limit: z.number().int().min(1).max(10000).default(1000),
      },
    },
    async ({ snapshot_date, start_date, end_date, account_ids, asins, low_stock_only, limit }) => jsonContent(
      await createClient().getInventory({
        snapshotDate: snapshot_date,
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        asins,
        lowStockOnly: low_stock_only,
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_advertising_metrics",
    {
      description: "Get raw advertising metric rows (impressions, clicks, cost, sales, ACoS, RoAS) per campaign and date.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        campaign_types: z.array(z.string()).optional(),
        limit: z.number().int().min(1).max(10000).default(1000),
        offset: z.number().int().min(0).default(0),
      },
    },
    async ({ start_date, end_date, account_ids, campaign_types, limit, offset }) => jsonContent(
      await createClient().getAdvertisingMetrics({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        campaignTypes: campaign_types,
        limit,
        offset,
      }),
    ),
  );

  // ===========================================================================
  // Catalog
  // ===========================================================================

  server.registerTool(
    "list_products",
    {
      description: "List products in the organization catalog with optional search/category/account filters.",
      inputSchema: {
        account_ids: z.array(uuidString).optional(),
        search: z.string().optional(),
        category: z.string().optional(),
        active_only: z.boolean().default(true),
        limit: z.number().int().min(1).max(500).default(100),
        offset: z.number().int().min(0).default(0),
      },
    },
    async ({ account_ids, search, category, active_only, limit, offset }) => jsonContent(
      await createClient().listProducts({
        accountIds: resolveAccountIds(account_ids),
        search,
        category,
        activeOnly: active_only,
        limit,
        offset,
      }),
    ),
  );

  server.registerTool(
    "get_product",
    {
      description: "Get a single product by ASIN.",
      inputSchema: { asin: z.string() },
    },
    async ({ asin }) => jsonContent(await createClient().getProduct(asin)),
  );

  server.registerTool(
    "update_product",
    {
      description: "Update editable catalog fields on a product (title, brand, category, active flag).",
      inputSchema: {
        asin: z.string(),
        title: z.string().optional(),
        brand: z.string().optional(),
        category: z.string().optional(),
        is_active: z.boolean().optional(),
      },
    },
    async ({ asin, title, brand, category, is_active }) => jsonContent(
      await createClient().updateProduct(asin, { title, brand, category, isActive: is_active }),
    ),
  );

  server.registerTool(
    "bulk_update_prices",
    {
      description: "Bulk-update prices for one account. Each update may target ASIN or SKU.",
      inputSchema: {
        account_id: uuidString,
        updates: z.array(
          z.object({
            asin: z.string().optional(),
            sku: z.string().optional(),
            price: z.number(),
          }),
        ).min(1),
        product_type: z.string().default("PRODUCT"),
      },
    },
    async ({ account_id, updates, product_type }) => jsonContent(
      await createClient().bulkUpdatePrices({ accountId: account_id, updates, productType: product_type }),
    ),
  );

  server.registerTool(
    "update_product_availability",
    {
      description: "Toggle availability and (optionally) set quantity for a product on one account.",
      inputSchema: {
        asin: z.string(),
        account_id: uuidString,
        is_available: z.boolean(),
        quantity: z.number().int().min(0).optional(),
        product_type: z.string().default("PRODUCT"),
      },
    },
    async ({ asin, account_id, is_available, quantity, product_type }) => jsonContent(
      await createClient().updateProductAvailability({
        asin,
        accountId: account_id,
        isAvailable: is_available,
        quantity,
        productType: product_type,
      }),
    ),
  );

  server.registerTool(
    "list_product_images",
    {
      description: "List Amazon product images for a given ASIN under one account.",
      inputSchema: {
        asin: z.string(),
        account_id: uuidString,
      },
    },
    async ({ asin, account_id }) => jsonContent(await createClient().listProductImages(asin, account_id)),
  );

  server.registerTool(
    "delete_product_image",
    {
      description: "Delete one product image identified by its storage key.",
      inputSchema: {
        asin: z.string(),
        account_id: uuidString,
        key: z.string(),
      },
    },
    async ({ asin, account_id, key }) => jsonContent(
      await createClient().deleteProductImage(asin, account_id, key),
    ),
  );

  // ===========================================================================
  // Analytics
  // ===========================================================================

  server.registerTool(
    "get_dashboard_kpis",
    {
      description: "Get the dashboard KPIs (revenue, units, orders, AOV, return rate, ROAS, ACoS, CTR) for a date range.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
      },
    },
    async ({ start_date, end_date, account_ids }) => jsonContent(
      await createClient().getDashboard({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
      }),
    ),
  );

  server.registerTool(
    "get_trends",
    {
      description: "Get trend series for one or more metrics (e.g. revenue, units, orders).",
      inputSchema: {
        metrics: z.array(z.string()).min(1).default(["revenue", "units"]),
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
      },
    },
    async ({ metrics, start_date, end_date, account_ids }) => jsonContent(
      await createClient().getTrends({
        metrics,
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
      }),
    ),
  );

  server.registerTool(
    "get_top_performers",
    {
      description: "Top performing products grouped by revenue, units and growth.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        limit: z.number().int().min(1).max(50).default(10),
      },
    },
    async ({ start_date, end_date, account_ids, limit }) => jsonContent(
      await createClient().getTopPerformers({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_period_comparison",
    {
      description: "Compare two arbitrary date ranges and get diffs/trends per metric.",
      inputSchema: {
        period1_start: dateString,
        period1_end: dateString,
        period2_start: dateString,
        period2_end: dateString,
        account_ids: z.array(uuidString).optional(),
        category: z.string().optional(),
        preset: z.string().optional(),
      },
    },
    async ({ period1_start, period1_end, period2_start, period2_end, account_ids, category, preset }) => jsonContent(
      await createClient().getComparison({
        period1Start: period1_start,
        period1End: period1_end,
        period2Start: period2_start,
        period2End: period2_end,
        accountIds: resolveAccountIds(account_ids),
        category,
        preset,
      }),
    ),
  );

  server.registerTool(
    "get_product_trends",
    {
      description: "Get product-level trend classification (rising/stable/declining) with optional AI insights.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_id: uuidString.optional(),
        account_ids: z.array(uuidString).optional(),
        asin: z.string().optional(),
        trend_class: z.enum(["rising_fast", "rising", "stable", "declining", "declining_fast"]).optional(),
        language: z.enum(["en", "it"]).default("en"),
        limit: z.number().int().min(1).max(100).default(50),
      },
    },
    async ({ start_date, end_date, account_id, account_ids, asin, trend_class, language, limit }) => jsonContent(
      await createClient().getProductTrends({
        startDate: start_date,
        endDate: end_date,
        accountId: account_id,
        accountIds: resolveAccountIds(account_ids),
        asin,
        trendClass: trend_class,
        language,
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_sales_by_category",
    {
      description: "Sales totals grouped by product category.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        category: z.string().optional(),
        limit: z.number().int().min(1).max(100).default(20),
      },
    },
    async ({ start_date, end_date, account_ids, category, limit }) => jsonContent(
      await createClient().getSalesByCategory({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        category,
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_orders_by_hour",
    {
      description: "Orders count distribution across the 24 hours of the day.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        max_pages_per_account: z.number().int().min(1).max(50).default(10),
      },
    },
    async ({ start_date, end_date, account_ids, max_pages_per_account }) => jsonContent(
      await createClient().getOrdersByHour({
        startDate: start_date,
        endDate: end_date,
        accountIds: resolveAccountIds(account_ids),
        maxPagesPerAccount: max_pages_per_account,
      }),
    ),
  );

  server.registerTool(
    "get_advertising_insights",
    {
      description: "Aggregated advertising insights with top/underperforming campaigns and recommendations.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
      },
    },
    async ({ start_date, end_date }) => jsonContent(
      await createClient().getAdvertisingInsights({ startDate: start_date, endDate: end_date }),
    ),
  );

  server.registerTool(
    "get_returns_analytics",
    {
      description: "Returns analytics: rate over time, reason breakdown, top ASINs by returns / return rate.",
      inputSchema: {
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_id: uuidString.optional(),
        account_ids: z.array(uuidString).optional(),
        asin: z.string().optional(),
        limit: z.number().int().min(1).max(50).default(10),
      },
    },
    async ({ start_date, end_date, account_id, account_ids, asin, limit }) => jsonContent(
      await createClient().getReturnsAnalytics({
        startDate: start_date,
        endDate: end_date,
        accountId: account_id,
        accountIds: resolveAccountIds(account_ids),
        asin,
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_ads_vs_organic",
    {
      description: "Split sales between advertising-attributed and organic, with optional ASIN breakdown.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_id: uuidString.optional(),
        account_ids: z.array(uuidString).optional(),
        group_by: z.enum(["day", "week", "month"]).default("day"),
        asin: z.string().optional(),
      },
    },
    async ({ start_date, end_date, account_id, account_ids, group_by, asin }) => jsonContent(
      await createClient().getAdsVsOrganic({
        startDate: start_date,
        endDate: end_date,
        accountId: account_id,
        accountIds: resolveAccountIds(account_ids),
        groupBy: group_by,
        asin,
      }),
    ),
  );

  // ===========================================================================
  // Forecasts
  // ===========================================================================

  server.registerTool(
    "list_forecasts",
    {
      description: "List stored forecasts for the organization.",
      inputSchema: {
        account_ids: z.array(uuidString).optional(),
        forecast_type: z.string().optional(),
        limit: z.number().int().min(1).max(100).default(20),
      },
    },
    async ({ account_ids, forecast_type, limit }) => jsonContent(
      await createClient().listForecasts({
        accountIds: resolveAccountIds(account_ids),
        forecastType: forecast_type,
        limit,
      }),
    ),
  );

  server.registerTool(
    "get_forecast",
    {
      description: "Get one forecast by ID, including predictions and historical baseline.",
      inputSchema: { forecast_id: uuidString },
    },
    async ({ forecast_id }) => jsonContent(await createClient().getForecast(forecast_id)),
  );

  server.registerTool(
    "get_product_forecast",
    {
      description: "Get the latest forecast for a single ASIN (across all accounts).",
      inputSchema: { asin: z.string() },
    },
    async ({ asin }) => jsonContent(await createClient().getProductForecast(asin)),
  );

  server.registerTool(
    "list_forecastable_products",
    {
      description: "List products that have enough sales history to be forecasted for an account.",
      inputSchema: {
        account_id: uuidString,
        lookback_days: z.number().int().min(30).max(730).default(365),
        min_history_days: z.number().int().min(1).max(30).default(7),
        limit: z.number().int().min(1).max(5000).default(1000),
      },
    },
    async ({ account_id, lookback_days, min_history_days, limit }) => jsonContent(
      await createClient().listForecastableProducts({
        accountId: account_id,
        lookbackDays: lookback_days,
        minHistoryDays: min_history_days,
        limit,
      }),
    ),
  );

  server.registerTool(
    "generate_forecast",
    {
      description: "Generate a new forecast for an account, optionally scoped to an ASIN.",
      inputSchema: {
        account_id: uuidString,
        asin: z.string().optional(),
        forecast_type: z.string().default("sales"),
        horizon_days: z.number().int().min(1).max(365).default(30),
      },
    },
    async ({ account_id, asin, forecast_type, horizon_days }) => jsonContent(
      await createClient().generateForecast({
        accountId: account_id,
        asin,
        forecastType: forecast_type,
        horizonDays: horizon_days,
      }),
    ),
  );

  // ===========================================================================
  // Alerts
  // ===========================================================================

  server.registerTool(
    "list_alert_rules",
    {
      description: "List configured alert rules.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().listAlertRules()),
  );

  server.registerTool(
    "create_alert_rule",
    {
      description: "Create a new alert rule.",
      inputSchema: {
        name: z.string(),
        alert_type: z.enum(["low_stock", "bsr_drop", "price_change", "sync_failure", "product_trend"]),
        conditions: z.record(z.unknown()),
        applies_to_accounts: z.array(uuidString).optional(),
        applies_to_asins: z.array(z.string()).optional(),
        notification_channels: z.array(z.string()).default(["email"]),
        notification_emails: z.array(z.string().email()).optional(),
        webhook_url: z.string().url().optional(),
        is_enabled: z.boolean().default(true),
      },
    },
    async (input) => jsonContent(await createClient().createAlertRule(input)),
  );

  server.registerTool(
    "update_alert_rule",
    {
      description: "Update an existing alert rule.",
      inputSchema: {
        rule_id: uuidString,
        name: z.string().optional(),
        conditions: z.record(z.unknown()).optional(),
        applies_to_accounts: z.array(uuidString).optional(),
        applies_to_asins: z.array(z.string()).optional(),
        notification_channels: z.array(z.string()).optional(),
        notification_emails: z.array(z.string().email()).optional(),
        webhook_url: z.string().url().optional(),
        is_enabled: z.boolean().optional(),
      },
    },
    async ({ rule_id, ...rest }) => jsonContent(await createClient().updateAlertRule(rule_id, rest)),
  );

  server.registerTool(
    "delete_alert_rule",
    {
      description: "Delete an alert rule.",
      inputSchema: { rule_id: uuidString },
    },
    async ({ rule_id }) => {
      await createClient().deleteAlertRule(rule_id);
      return jsonContent({ status: "deleted", rule_id });
    },
  );

  server.registerTool(
    "get_alert_summary",
    {
      description: "Counts of unread/critical alerts and active rules.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().getAlertSummary()),
  );

  server.registerTool(
    "list_alerts",
    {
      description: "List alerts with filters (severity, status, type, account, ASIN).",
      inputSchema: {
        severity: z.enum(["info", "warning", "critical"]).optional(),
        status: z.enum(["unread", "read", "all"]).default("unread"),
        type: z.enum(["low_stock", "bsr_drop", "price_change", "sync_failure", "product_trend"]).optional(),
        account_id: uuidString.optional(),
        asin: z.string().optional(),
        limit: z.number().int().min(1).max(100).default(50),
        offset: z.number().int().min(0).default(0),
      },
    },
    async (input) => jsonContent(await createClient().listAlerts(input)),
  );

  server.registerTool(
    "mark_alert_read",
    {
      description: "Mark a single alert as read or unread.",
      inputSchema: {
        alert_id: uuidString,
        read: z.boolean().default(true),
      },
    },
    async ({ alert_id, read }) => jsonContent(await createClient().markAlertRead(alert_id, read)),
  );

  server.registerTool(
    "mark_all_alerts_read",
    {
      description: "Mark every alert as read (or unread) in bulk.",
      inputSchema: { read: z.boolean().default(true) },
    },
    async ({ read }) => jsonContent(await createClient().bulkMarkAlerts(read, "all")),
  );

  // ===========================================================================
  // Scheduled reports
  // ===========================================================================

  server.registerTool(
    "list_scheduled_reports",
    {
      description: "List scheduled report definitions.",
      inputSchema: {},
    },
    async () => jsonContent(await createClient().listScheduledReports()),
  );

  server.registerTool(
    "get_scheduled_report",
    {
      description: "Get a scheduled report by ID.",
      inputSchema: { schedule_id: uuidString },
    },
    async ({ schedule_id }) => jsonContent(await createClient().getScheduledReport(schedule_id)),
  );

  server.registerTool(
    "list_scheduled_report_runs",
    {
      description: "List recent runs for a scheduled report.",
      inputSchema: {
        schedule_id: uuidString,
        limit: z.number().int().min(1).max(100).default(20),
      },
    },
    async ({ schedule_id, limit }) => jsonContent(
      await createClient().listScheduledReportRuns(schedule_id, limit),
    ),
  );

  server.registerTool(
    "run_scheduled_report_now",
    {
      description: "Trigger an out-of-band run for a scheduled report.",
      inputSchema: { schedule_id: uuidString },
    },
    async ({ schedule_id }) => jsonContent(await createClient().runScheduledReportNow(schedule_id)),
  );

  server.registerTool(
    "toggle_scheduled_report",
    {
      description: "Enable or disable a scheduled report.",
      inputSchema: {
        schedule_id: uuidString,
        enabled: z.boolean(),
      },
    },
    async ({ schedule_id, enabled }) => jsonContent(
      await createClient().toggleScheduledReport(schedule_id, enabled),
    ),
  );

  server.registerTool(
    "download_scheduled_run_artifact",
    {
      description: "Download the artifact produced by a scheduled report run; saved under the local exports dir.",
      inputSchema: { run_id: uuidString },
    },
    async ({ run_id }) => {
      const download = await createClient().downloadScheduledRunArtifact(run_id);
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  // ===========================================================================
  // Market research
  // ===========================================================================

  server.registerTool(
    "list_market_research",
    {
      description: "List market research reports.",
      inputSchema: {
        limit: z.number().int().min(1).max(200).default(20),
        offset: z.number().int().min(0).default(0),
      },
    },
    async ({ limit, offset }) => jsonContent(await createClient().listMarketResearch(limit, offset)),
  );

  server.registerTool(
    "get_market_research",
    {
      description: "Get a market research report by ID, including competitor data and AI analysis.",
      inputSchema: { report_id: uuidString },
    },
    async ({ report_id }) => jsonContent(await createClient().getMarketResearch(report_id)),
  );

  server.registerTool(
    "generate_market_research",
    {
      description: "Generate a new market research report.",
      inputSchema: {
        account_id: uuidString,
        source_asin: z.string().optional(),
        language: z.enum(["en", "it"]).default("en"),
        extra_competitor_asins: z.array(z.string()).max(5).optional(),
        market_competitor_asins: z.array(z.string()).max(15).optional(),
        search_query: z.string().max(200).optional(),
        search_type: z.enum(["keyword", "brand", "asin"]).optional(),
      },
    },
    async (input) => jsonContent(await createClient().generateMarketResearch(input)),
  );

  server.registerTool(
    "refresh_market_research",
    {
      description: "Refresh competitor and AI data for an existing market research report.",
      inputSchema: { report_id: uuidString },
    },
    async ({ report_id }) => jsonContent(await createClient().refreshMarketResearch(report_id)),
  );

  server.registerTool(
    "get_market_research_matrix",
    {
      description: "Get the comparison matrix (dimensions, scores, opportunities) for a report.",
      inputSchema: { report_id: uuidString },
    },
    async ({ report_id }) => jsonContent(await createClient().getMarketResearchMatrix(report_id)),
  );

  server.registerTool(
    "delete_market_research",
    {
      description: "Delete a market research report.",
      inputSchema: { report_id: uuidString },
    },
    async ({ report_id }) => jsonContent(await createClient().deleteMarketResearch(report_id)),
  );

  server.registerTool(
    "market_search",
    {
      description: "Search Amazon catalog (keyword/brand/ASIN) via the market research search endpoint.",
      inputSchema: {
        account_id: uuidString,
        search_type: z.enum(["keyword", "brand", "asin"]),
        query: z.string(),
        language: z.enum(["en", "it"]).default("en"),
      },
    },
    async (input) => jsonContent(await createClient().marketSearch(input)),
  );

  server.registerTool(
    "suggest_competitors",
    {
      description: "Get competitor ASIN suggestions, optionally filtered by category and marketplace.",
      inputSchema: {
        category: z.string().optional(),
        marketplace: z.string().optional(),
      },
    },
    async (input) => jsonContent(await createClient().suggestCompetitors(input)),
  );

  // ===========================================================================
  // Recommendations
  // ===========================================================================

  server.registerTool(
    "list_recommendations",
    {
      description: "List strategic recommendations with optional status/category/account filters.",
      inputSchema: {
        status: z.enum(["pending", "implemented", "dismissed"]).optional(),
        category: z.enum(["pricing", "advertising", "inventory", "content"]).optional(),
        account_id: uuidString.optional(),
        limit: z.number().int().min(1).max(200).default(50),
        offset: z.number().int().min(0).default(0),
      },
    },
    async (input) => jsonContent(await createClient().listRecommendations(input)),
  );

  server.registerTool(
    "get_recommendation",
    {
      description: "Get a single strategic recommendation by ID.",
      inputSchema: { rec_id: uuidString },
    },
    async ({ rec_id }) => jsonContent(await createClient().getRecommendation(rec_id)),
  );

  server.registerTool(
    "update_recommendation_status",
    {
      description: "Update the status of a recommendation (implemented / dismissed / pending), with optional outcome notes.",
      inputSchema: {
        rec_id: uuidString,
        status: z.enum(["pending", "implemented", "dismissed"]),
        outcome_notes: z.string().optional(),
      },
    },
    async ({ rec_id, status, outcome_notes }) => jsonContent(
      await createClient().updateRecommendationStatus(rec_id, { status, outcomeNotes: outcome_notes }),
    ),
  );

  server.registerTool(
    "generate_recommendations",
    {
      description: "Generate fresh strategic recommendations based on the last N days of activity.",
      inputSchema: {
        lookback_days: z.number().int().min(7).max(180).default(28),
        language: z.enum(["en", "it"]).default("en"),
        account_id: uuidString.optional(),
        asin: z.string().optional(),
      },
    },
    async ({ lookback_days, language, account_id, asin }) => jsonContent(
      await createClient().generateRecommendations({
        lookbackDays: lookback_days,
        language,
        accountId: account_id,
        asin,
      }),
    ),
  );

  // ===========================================================================
  // Exports (binary, saved to local exports dir)
  // ===========================================================================

  server.registerTool(
    "export_csv",
    {
      description: "Generate a ZIP of CSV files for one report type and save it under the local exports dir.",
      inputSchema: {
        report_type: z.enum(["sales", "inventory", "advertising"]),
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        group_by: z.enum(["day", "week", "month"]).optional(),
        low_stock_only: z.boolean().optional(),
        language: z.enum(["en", "it"]).optional(),
        include_comparison: z.boolean().optional(),
      },
    },
    async (input) => {
      const download = await createClient().exportCsv({
        reportType: input.report_type,
        startDate: input.start_date,
        endDate: input.end_date,
        accountIds: resolveAccountIds(input.account_ids),
        groupBy: input.group_by,
        lowStockOnly: input.low_stock_only,
        language: input.language,
        includeComparison: input.include_comparison,
      });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_bundle",
    {
      description: "Generate a ZIP bundle containing CSVs for multiple report types.",
      inputSchema: {
        report_types: z.array(z.enum(["sales", "inventory", "advertising"])).min(1),
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        group_by: z.enum(["day", "week", "month"]).optional(),
        low_stock_only: z.boolean().optional(),
        language: z.enum(["en", "it"]).optional(),
        include_comparison: z.boolean().optional(),
      },
    },
    async (input) => {
      const download = await createClient().exportBundle({
        reportTypes: input.report_types,
        startDate: input.start_date,
        endDate: input.end_date,
        accountIds: resolveAccountIds(input.account_ids),
        groupBy: input.group_by,
        lowStockOnly: input.low_stock_only,
        language: input.language,
        includeComparison: input.include_comparison,
      });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_excel_bundle",
    {
      description: "Generate a multi-sheet Excel bundle for one or more report types and save it locally.",
      inputSchema: {
        report_types: z.array(z.enum(["sales", "inventory", "advertising"])).min(1),
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        group_by: z.enum(["day", "week", "month"]).optional(),
        low_stock_only: z.boolean().optional(),
        language: z.enum(["en", "it"]).optional(),
        include_comparison: z.boolean().optional(),
        template: z.enum(["clean", "corporate", "executive"]).default("clean"),
      },
    },
    async (input) => {
      const download = await createClient().exportExcelBundle({
        reportTypes: input.report_types,
        startDate: input.start_date,
        endDate: input.end_date,
        accountIds: resolveAccountIds(input.account_ids),
        groupBy: input.group_by,
        lowStockOnly: input.low_stock_only,
        language: input.language,
        includeComparison: input.include_comparison,
        template: input.template,
      });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_excel",
    {
      description: "Generate a single Excel report (sales + advertising flags) and save it locally.",
      inputSchema: {
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        include_sales: z.boolean().default(true),
        include_advertising: z.boolean().default(true),
      },
    },
    async (input) => {
      const download = await createClient().exportExcel({
        startDate: input.start_date,
        endDate: input.end_date,
        accountIds: resolveAccountIds(input.account_ids),
        includeSales: input.include_sales,
        includeAdvertising: input.include_advertising,
      });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_powerpoint",
    {
      description: "Generate a PowerPoint executive deck for the date range and save it locally.",
      inputSchema: {
        start_date: dateString.optional(),
        end_date: dateString.optional(),
        account_ids: z.array(uuidString).optional(),
        template: z.string().default("default"),
      },
    },
    async (input) => {
      const download = await createClient().exportPowerPoint({
        startDate: input.start_date,
        endDate: input.end_date,
        accountIds: resolveAccountIds(input.account_ids),
        template: input.template,
      });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_forecast_excel",
    {
      description: "Export an existing forecast as a styled Excel file.",
      inputSchema: {
        forecast_id: uuidString,
        template: z.enum(["clean", "corporate", "executive"]).default("clean"),
        language: z.enum(["en", "it"]).default("en"),
      },
    },
    async ({ forecast_id, template, language }) => {
      const download = await createClient().exportForecastExcel({ forecastId: forecast_id, template, language });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "export_market_research_pdf",
    {
      description: "Export a market research report as a PDF.",
      inputSchema: {
        report_id: uuidString,
        language: z.enum(["en", "it"]).default("en"),
      },
    },
    async ({ report_id, language }) => {
      const download = await createClient().exportMarketResearchPdf({ reportId: report_id, language });
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  server.registerTool(
    "create_forecast_package_job",
    {
      description: "Create an async forecast-package export job (Excel + insights). Poll with get_forecast_package_job.",
      inputSchema: {
        forecast_id: uuidString,
        template: z.enum(["clean", "corporate", "executive"]).default("clean"),
        language: z.enum(["en", "it"]).default("en"),
        include_insights: z.boolean().default(true),
      },
    },
    async ({ forecast_id, template, language, include_insights }) => jsonContent(
      await createClient().createForecastPackageJob({
        forecastId: forecast_id,
        template,
        language,
        includeInsights: include_insights,
      }),
    ),
  );

  server.registerTool(
    "get_forecast_package_job",
    {
      description: "Poll the status of a forecast-package export job.",
      inputSchema: { job_id: uuidString },
    },
    async ({ job_id }) => jsonContent(await createClient().getForecastPackageJob(job_id)),
  );

  server.registerTool(
    "download_forecast_package",
    {
      description: "Download the artifact of a completed forecast-package job and save it locally.",
      inputSchema: { job_id: uuidString },
    },
    async ({ job_id }) => {
      const download = await createClient().downloadForecastPackage(job_id);
      const path = saveBinary(download);
      return jsonContent({ saved_to: path, filename: download.filename, content_type: download.contentType });
    },
  );

  // ===========================================================================
  // Convenience composite tools
  // ===========================================================================

  server.registerTool(
    "snapshot",
    {
      description:
        "High-level org snapshot for a date range: dashboard KPIs, account summary, top performers and unread alert count.",
      inputSchema: {
        start_date: dateString,
        end_date: dateString,
        account_ids: z.array(uuidString).optional(),
        top_limit: z.number().int().min(1).max(20).default(5),
      },
    },
    async ({ start_date, end_date, account_ids, top_limit }) => {
      const client = createClient();
      const accountIds = resolveAccountIds(account_ids);
      const [dashboard, accounts, top, unread] = await Promise.all([
        client.getDashboard({ startDate: start_date, endDate: end_date, accountIds }),
        client.getAccountsSummary(),
        client.getTopPerformers({ startDate: start_date, endDate: end_date, accountIds, limit: top_limit }),
        client.getUnreadAlertCount(),
      ]);
      return jsonContent({
        period: { start: start_date, end: end_date },
        dashboard,
        accounts,
        top_performers: top,
        unread_alerts: unread.count,
      });
    },
  );

  // Suppress eslint about unused
  void textContent;
}
