import { BackendClient, loadLocalState, saveLocalState } from "@inthezon/shared-sdk";
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

export function registerInthezonTools(server: McpServer): void {
  server.registerTool(
    "list_accounts",
    {
      description: "List connected Amazon accounts for the authenticated Inthezon organization.",
      inputSchema: {},
    },
    async () => {
      const accounts = await createClient().listAccounts();
      return jsonContent(accounts);
    },
  );

  server.registerTool(
    "get_account_status",
    {
      description: "Get sync status for a single Amazon account.",
      inputSchema: {
        account_id: z.string().uuid().describe("Amazon account UUID."),
      },
    },
    async ({ account_id }) => {
      const account = await createClient().getAccountStatus(account_id);
      return jsonContent(account);
    },
  );

  server.registerTool(
    "get_accounts_summary",
    {
      description: "Return a summary of account counts grouped by sync state.",
      inputSchema: {},
    },
    async () => {
      const accounts = await createClient().listAccounts();
      const summary = {
        total: accounts.length,
        active: accounts.filter((account) => account.is_active).length,
        syncing: accounts.filter((account) => account.sync_status === "syncing").length,
        with_errors: accounts.filter((account) => account.sync_status === "error").length,
        synced_ok: accounts.filter((account) => account.sync_status === "success").length,
      };
      return jsonContent(summary);
    },
  );

  server.registerTool(
    "query_sales",
    {
      description: "Query sales rows for a date range, optionally filtered by account or ASIN.",
      inputSchema: {
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z.string().describe("End date in YYYY-MM-DD format."),
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
        asin: z.string().optional().describe("Optional ASIN filter."),
        limit: z.number().int().min(1).max(1000).default(100).describe("Maximum rows."),
      },
    },
    async ({ start_date, end_date, account_id, asin, limit }) => {
      const data = await createClient().getSales({
        startDate: start_date,
        endDate: end_date,
        accountIds: account_id ? [account_id] : undefined,
        asins: asin ? [asin] : undefined,
        limit,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "query_sales_aggregated",
    {
      description: "Aggregate sales data by day, week or month.",
      inputSchema: {
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z.string().describe("End date in YYYY-MM-DD format."),
        group_by: z.enum(["day", "week", "month"]).default("day"),
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
      },
    },
    async ({ start_date, end_date, group_by, account_id }) => {
      const data = await createClient().getSalesAggregated({
        startDate: start_date,
        endDate: end_date,
        groupBy: group_by,
        accountIds: account_id ? [account_id] : undefined,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "get_inventory",
    {
      description: "Get inventory snapshot data, optionally filtered by account or ASIN.",
      inputSchema: {
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
        asin: z.string().optional().describe("Optional ASIN filter."),
      },
    },
    async ({ account_id, asin }) => {
      const data = await createClient().getInventory({
        accountIds: account_id ? [account_id] : undefined,
        asins: asin ? [asin] : undefined,
        limit: 1000,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "list_products",
    {
      description: "List products in the authenticated organization catalog.",
      inputSchema: {
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
        search: z.string().optional().describe("Search in ASIN, SKU or title."),
        limit: z.number().int().min(1).max(500).default(50),
      },
    },
    async ({ account_id, search, limit }) => {
      const data = await createClient().listProducts({
        accountIds: account_id ? [account_id] : undefined,
        search,
        limit,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "get_dashboard_kpis",
    {
      description: "Get dashboard KPIs for the selected date range.",
      inputSchema: {
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z.string().describe("End date in YYYY-MM-DD format."),
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
      },
    },
    async ({ start_date, end_date, account_id }) => {
      const data = await createClient().getDashboard({
        startDate: start_date,
        endDate: end_date,
        accountIds: account_id ? [account_id] : undefined,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "get_trends",
    {
      description: "Get trend series for revenue, units or orders.",
      inputSchema: {
        metric: z.enum(["revenue", "units", "orders"]).describe("Metric to trend."),
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z.string().describe("End date in YYYY-MM-DD format."),
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
      },
    },
    async ({ metric, start_date, end_date, account_id }) => {
      const data = await createClient().getTrends({
        metrics: [metric],
        startDate: start_date,
        endDate: end_date,
        accountIds: account_id ? [account_id] : undefined,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "get_top_products",
    {
      description: "Get top products by revenue or units for a date range.",
      inputSchema: {
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z.string().describe("End date in YYYY-MM-DD format."),
        sort_by: z.enum(["revenue", "units"]).default("revenue"),
        limit: z.number().int().min(1).max(50).default(10),
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
      },
    },
    async ({ start_date, end_date, sort_by, limit, account_id }) => {
      const data = await createClient().getTopPerformers({
        startDate: start_date,
        endDate: end_date,
        accountIds: account_id ? [account_id] : undefined,
        limit,
      });
      return jsonContent(sort_by === "units" ? data.by_units : data.by_revenue);
    },
  );

  server.registerTool(
    "get_forecasts",
    {
      description: "List stored forecasts for the authenticated organization.",
      inputSchema: {
        account_id: z.string().uuid().optional().describe("Optional Amazon account UUID."),
        forecast_type: z.string().optional().describe("Optional forecast type."),
        limit: z.number().int().min(1).max(100).default(20),
      },
    },
    async ({ account_id, forecast_type, limit }) => {
      const data = await createClient().listForecasts({
        accountIds: account_id ? [account_id] : undefined,
        forecastType: forecast_type,
        limit,
      });
      return jsonContent(data);
    },
  );

  server.registerTool(
    "generate_forecast",
    {
      description: "Generate a new forecast for an account, optionally scoped to an ASIN.",
      inputSchema: {
        account_id: z.string().uuid().describe("Amazon account UUID."),
        asin: z.string().optional().describe("Optional ASIN."),
        horizon_days: z.number().int().min(1).max(365).default(30),
      },
    },
    async ({ account_id, asin, horizon_days }) => {
      const data = await createClient().generateForecast({
        accountId: account_id,
        asin,
        horizonDays: horizon_days,
      });
      return jsonContent(data);
    },
  );
}
