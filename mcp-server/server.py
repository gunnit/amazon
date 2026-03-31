"""Inthezon MCP Server — exposes Amazon data as tools for AI assistants."""

import io
import csv
import random
import math
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

from db import get_session
from helpers import to_json, rows_to_list, row_to_dict

mcp = FastMCP("inthezon", instructions="Inthezon Amazon data — vendas, estoque, produtos, ads, forecasts.")


def _get_context() -> dict:
    """Load selected account IDs from the active config profile."""
    try:
        from config import get_active_profile
        _, profile = get_active_profile()
        return {"selected_account_ids": profile.get("selected_account_ids", [])}
    except Exception:
        return {"selected_account_ids": []}


# ─── Accounts ────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_accounts() -> str:
    """List all Amazon accounts with id, name, type, marketplace, and sync status."""
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, account_name, account_type, marketplace_id, marketplace_country, "
            "is_active, sync_status, last_sync_at "
            "FROM amazon_accounts ORDER BY account_name"
        ))
        return to_json(rows_to_list(result))


@mcp.tool()
async def get_account_status(account_id: str) -> str:
    """Get sync status, last error, and last sync time for a specific account."""
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, account_name, sync_status, sync_error_message, last_sync_at, updated_at "
            "FROM amazon_accounts WHERE id = :aid"
        ), {"aid": account_id})
        row = result.first()
        if not row:
            return to_json({"error": "Account not found"})
        return to_json(row_to_dict(row))


@mcp.tool()
async def get_accounts_summary() -> str:
    """Get summary counts: total accounts, active, syncing, with errors."""
    async with get_session() as db:
        result = await db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_active) AS active,
                COUNT(*) FILTER (WHERE sync_status = 'SYNCING') AS syncing,
                COUNT(*) FILTER (WHERE sync_status = 'ERROR') AS with_errors,
                COUNT(*) FILTER (WHERE sync_status = 'SUCCESS') AS synced_ok
            FROM amazon_accounts
        """))
        return to_json(row_to_dict(result.one()))


# ─── Sales ───────────────────────────────────────────────────────────────────


@mcp.tool()
async def query_sales(
    start_date: str,
    end_date: str,
    account_id: str | None = None,
    asin: str | None = None,
    limit: int = 100,
) -> str:
    """Query sales data rows. Returns date, asin, units, revenue, currency.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        account_id: Optional account UUID filter.
        asin: Optional ASIN filter.
        limit: Max rows (default 100).
    """
    clauses = ["date >= :start AND date <= :end"]
    params: dict = {"start": start_date, "end": end_date, "lim": min(limit, 1000)}
    if account_id:
        clauses.append("account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    if asin:
        clauses.append("asin = :asin")
        params["asin"] = asin
    where = " AND ".join(clauses)
    async with get_session() as db:
        result = await db.execute(text(
            f"SELECT date, account_id, asin, sku, units_ordered, "
            f"ordered_product_sales, currency "
            f"FROM sales_data WHERE {where} ORDER BY date DESC LIMIT :lim"
        ), params)
        return to_json(rows_to_list(result))


@mcp.tool()
async def query_sales_aggregated(
    start_date: str,
    end_date: str,
    group_by: str = "day",
    account_id: str | None = None,
) -> str:
    """Aggregate sales by period (day/week/month).

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        group_by: Aggregation period — day, week, or month.
        account_id: Optional account UUID filter.
    """
    trunc_map = {"day": "day", "week": "week", "month": "month"}
    trunc = trunc_map.get(group_by, "day")
    clauses = ["date >= :start AND date <= :end"]
    params: dict = {"start": start_date, "end": end_date}
    if account_id:
        clauses.append("account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    where = " AND ".join(clauses)
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT date_trunc(:trunc, date::timestamp)::date AS period,
                   SUM(units_ordered) AS total_units,
                   SUM(ordered_product_sales) AS total_revenue,
                   COUNT(DISTINCT asin) AS unique_asins
            FROM sales_data
            WHERE {where}
            GROUP BY 1 ORDER BY 1
        """), {**params, "trunc": trunc})
        return to_json(rows_to_list(result))


# ─── Inventory ───────────────────────────────────────────────────────────────


@mcp.tool()
async def get_inventory(
    account_id: str | None = None,
    asin: str | None = None,
) -> str:
    """Get current inventory snapshot (latest per ASIN) with FBA quantities.

    Args:
        account_id: Optional account UUID filter.
        asin: Optional ASIN filter.
    """
    clauses = []
    params: dict = {}
    if account_id:
        clauses.append("i.account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("i.account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    if asin:
        clauses.append("i.asin = :asin")
        params["asin"] = asin
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT DISTINCT ON (i.account_id, i.asin)
                i.account_id, i.asin, i.sku, i.snapshot_date,
                i.afn_fulfillable_quantity, i.afn_inbound_working_quantity,
                i.afn_inbound_shipped_quantity, i.afn_reserved_quantity,
                i.afn_total_quantity, i.mfn_fulfillable_quantity
            FROM inventory_data i
            {where}
            ORDER BY i.account_id, i.asin, i.snapshot_date DESC
        """), params)
        return to_json(rows_to_list(result))


@mcp.tool()
async def get_low_stock_alerts(
    threshold: int = 10,
    account_id: str | None = None,
) -> str:
    """Products with fulfillable stock below threshold.

    Args:
        threshold: Stock threshold (default 10).
        account_id: Optional account UUID filter.
    """
    clauses = ["sub.afn_fulfillable_quantity < :threshold"]
    params: dict = {"threshold": threshold}
    if account_id:
        clauses.append("sub.account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("sub.account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    where = " AND ".join(clauses)
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT sub.* FROM (
                SELECT DISTINCT ON (account_id, asin)
                    account_id, asin, sku, snapshot_date,
                    afn_fulfillable_quantity, afn_total_quantity
                FROM inventory_data
                ORDER BY account_id, asin, snapshot_date DESC
            ) sub
            WHERE {where}
            ORDER BY sub.afn_fulfillable_quantity ASC
        """), params)
        return to_json(rows_to_list(result))


# ─── Products ────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_products(
    account_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
) -> str:
    """List products with ASIN, title, brand, price, BSR.

    Args:
        account_id: Optional account UUID filter.
        search: Optional text search on title or brand.
        limit: Max results (default 50).
    """
    clauses = ["is_active = true"]
    params: dict = {"lim": min(limit, 500)}
    if account_id:
        clauses.append("account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    if search:
        clauses.append("(title ILIKE :q OR brand ILIKE :q OR asin ILIKE :q)")
        params["q"] = f"%{search}%"
    where = " AND ".join(clauses)
    async with get_session() as db:
        result = await db.execute(text(
            f"SELECT id, account_id, asin, sku, title, brand, category, "
            f"current_price, current_bsr, review_count, rating "
            f"FROM products WHERE {where} ORDER BY current_bsr ASC NULLS LAST LIMIT :lim"
        ), params)
        return to_json(rows_to_list(result))


@mcp.tool()
async def get_product_detail(asin: str) -> str:
    """Get full product details for a specific ASIN.

    Args:
        asin: The Amazon ASIN.
    """
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT * FROM products WHERE asin = :asin LIMIT 1"
        ), {"asin": asin})
        row = result.first()
        if not row:
            return to_json({"error": f"Product {asin} not found"})
        return to_json(row_to_dict(row))


@mcp.tool()
async def get_bsr_history(asin: str, days: int = 30) -> str:
    """Get BSR history for a product.

    Args:
        asin: The Amazon ASIN.
        days: Number of days of history (default 30).
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    async with get_session() as db:
        result = await db.execute(text("""
            SELECT bh.date, bh.category, bh.bsr
            FROM bsr_history bh
            JOIN products p ON p.id = bh.product_id
            WHERE p.asin = :asin AND bh.date >= :since
            ORDER BY bh.date
        """), {"asin": asin, "since": since})
        return to_json(rows_to_list(result))


# ─── Advertising ─────────────────────────────────────────────────────────────


@mcp.tool()
async def get_advertising_performance(
    start_date: str,
    end_date: str,
    account_id: str | None = None,
) -> str:
    """Aggregated advertising metrics: impressions, clicks, cost, CTR, CPC, ACOS, ROAS.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        account_id: Optional account UUID filter.
    """
    params: dict = {"start": start_date, "end": end_date}
    if account_id:
        acct_filter = "AND c.account_id = :aid"
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        acct_filter = "AND c.account_id = ANY(:ctx_aids)"
        params["ctx_aids"] = ctx_ids
    else:
        acct_filter = ""
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT
                SUM(m.impressions) AS impressions,
                SUM(m.clicks) AS clicks,
                SUM(m.cost) AS cost,
                SUM(m.attributed_sales_7d) AS attributed_sales,
                CASE WHEN SUM(m.impressions) > 0
                     THEN ROUND(SUM(m.clicks)::numeric / SUM(m.impressions) * 100, 4)
                     ELSE 0 END AS ctr,
                CASE WHEN SUM(m.clicks) > 0
                     THEN ROUND(SUM(m.cost) / SUM(m.clicks), 4)
                     ELSE 0 END AS cpc,
                CASE WHEN SUM(m.attributed_sales_7d) > 0
                     THEN ROUND(SUM(m.cost) / SUM(m.attributed_sales_7d) * 100, 4)
                     ELSE 0 END AS acos,
                CASE WHEN SUM(m.cost) > 0
                     THEN ROUND(SUM(m.attributed_sales_7d) / SUM(m.cost), 4)
                     ELSE 0 END AS roas
            FROM advertising_metrics m
            JOIN advertising_campaigns c ON c.id = m.campaign_id
            WHERE m.date >= :start AND m.date <= :end {acct_filter}
        """), params)
        return to_json(row_to_dict(result.one()))


@mcp.tool()
async def list_campaigns(
    account_id: str | None = None,
    state: str | None = None,
) -> str:
    """List advertising campaigns.

    Args:
        account_id: Optional account UUID filter.
        state: Optional state filter (enabled, paused, archived).
    """
    clauses = []
    params: dict = {}
    if account_id:
        clauses.append("account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    if state:
        clauses.append("state = :state")
        params["state"] = state
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with get_session() as db:
        result = await db.execute(text(
            f"SELECT id, account_id, campaign_id, campaign_name, campaign_type, "
            f"state, daily_budget, targeting_type "
            f"FROM advertising_campaigns {where} ORDER BY campaign_name"
        ), params)
        return to_json(rows_to_list(result))


# ─── Analytics / KPIs ────────────────────────────────────────────────────────


@mcp.tool()
async def get_dashboard_kpis(
    start_date: str,
    end_date: str,
    account_id: str | None = None,
) -> str:
    """Dashboard KPIs: revenue, units, orders + comparison with previous period.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        account_id: Optional account UUID filter.
    """
    sd = date.fromisoformat(start_date)
    ed = date.fromisoformat(end_date)
    delta = (ed - sd).days
    prev_start = (sd - timedelta(days=delta + 1)).isoformat()
    prev_end = (sd - timedelta(days=1)).isoformat()

    params: dict = {
        "cs": start_date, "ce": end_date,
        "ps": prev_start, "pe": prev_end,
    }
    if account_id:
        acct_filter = "AND account_id = :aid"
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        acct_filter = "AND account_id = ANY(:ctx_aids)"
        params["ctx_aids"] = ctx_ids
    else:
        acct_filter = ""

    async with get_session() as db:
        result = await db.execute(text(f"""
            WITH current_p AS (
                SELECT COALESCE(SUM(ordered_product_sales), 0) AS revenue,
                       COALESCE(SUM(units_ordered), 0) AS units,
                       COALESCE(SUM(total_order_items), 0) AS orders,
                       COUNT(DISTINCT asin) AS active_asins
                FROM sales_data
                WHERE date >= :cs AND date <= :ce {acct_filter}
            ), prev_p AS (
                SELECT COALESCE(SUM(ordered_product_sales), 0) AS revenue,
                       COALESCE(SUM(units_ordered), 0) AS units,
                       COALESCE(SUM(total_order_items), 0) AS orders,
                       COUNT(DISTINCT asin) AS active_asins
                FROM sales_data
                WHERE date >= :ps AND date <= :pe {acct_filter}
            )
            SELECT
                c.revenue, c.units, c.orders, c.active_asins,
                p.revenue AS prev_revenue, p.units AS prev_units,
                p.orders AS prev_orders,
                CASE WHEN p.revenue > 0
                     THEN ROUND((c.revenue - p.revenue) / p.revenue * 100, 2)
                     ELSE NULL END AS revenue_change_pct,
                CASE WHEN p.units > 0
                     THEN ROUND((c.units - p.units)::numeric / p.units * 100, 2)
                     ELSE NULL END AS units_change_pct
            FROM current_p c, prev_p p
        """), params)
        return to_json(row_to_dict(result.one()))


@mcp.tool()
async def get_trends(
    metric: str,
    start_date: str,
    end_date: str,
    account_id: str | None = None,
) -> str:
    """Time-series trend data points.

    Args:
        metric: Metric to trend — revenue, units, or orders.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        account_id: Optional account UUID filter.
    """
    col_map = {
        "revenue": "SUM(ordered_product_sales)",
        "units": "SUM(units_ordered)",
        "orders": "SUM(total_order_items)",
    }
    col = col_map.get(metric, "SUM(ordered_product_sales)")
    params: dict = {"start": start_date, "end": end_date}
    if account_id:
        acct_filter = "AND account_id = :aid"
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        acct_filter = "AND account_id = ANY(:ctx_aids)"
        params["ctx_aids"] = ctx_ids
    else:
        acct_filter = ""
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT date, {col} AS value
            FROM sales_data
            WHERE date >= :start AND date <= :end {acct_filter}
            GROUP BY date ORDER BY date
        """), params)
        return to_json(rows_to_list(result))


@mcp.tool()
async def get_top_products(
    start_date: str,
    end_date: str,
    sort_by: str = "revenue",
    limit: int = 10,
    account_id: str | None = None,
) -> str:
    """Top products by revenue or units sold.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        sort_by: Sort by 'revenue' or 'units'.
        limit: Number of top products (default 10).
        account_id: Optional account UUID filter.
    """
    order_col = "total_revenue" if sort_by == "revenue" else "total_units"
    params: dict = {"start": start_date, "end": end_date, "lim": min(limit, 100)}
    if account_id:
        acct_filter = "AND s.account_id = :aid"
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        acct_filter = "AND s.account_id = ANY(:ctx_aids)"
        params["ctx_aids"] = ctx_ids
    else:
        acct_filter = ""
    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT s.asin,
                   COALESCE(p.title, s.asin) AS title,
                   p.brand,
                   SUM(s.units_ordered) AS total_units,
                   SUM(s.ordered_product_sales) AS total_revenue,
                   s.currency
            FROM sales_data s
            LEFT JOIN products p ON p.asin = s.asin AND p.account_id = s.account_id
            WHERE s.date >= :start AND s.date <= :end {acct_filter}
            GROUP BY s.asin, p.title, p.brand, s.currency
            ORDER BY {order_col} DESC
            LIMIT :lim
        """), params)
        return to_json(rows_to_list(result))


# ─── Forecasts ───────────────────────────────────────────────────────────────


@mcp.tool()
async def get_forecasts(
    account_id: str | None = None,
    asin: str | None = None,
) -> str:
    """Get existing forecasts with predictions.

    Args:
        account_id: Optional account UUID filter.
        asin: Optional ASIN filter.
    """
    clauses = []
    params: dict = {}
    if account_id:
        clauses.append("account_id = :aid")
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        clauses.append("account_id = ANY(:ctx_aids)")
        params["ctx_aids"] = ctx_ids
    if asin:
        clauses.append("asin = :asin")
        params["asin"] = asin
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with get_session() as db:
        result = await db.execute(text(
            f"SELECT id, account_id, asin, forecast_type, generated_at, "
            f"forecast_horizon_days, model_used, confidence_interval, "
            f"predictions, mape, rmse "
            f"FROM forecasts {where} ORDER BY generated_at DESC"
        ), params)
        return to_json(rows_to_list(result))


@mcp.tool()
async def generate_forecast(
    account_id: str,
    asin: str | None = None,
    horizon_days: int = 30,
) -> str:
    """Generate a simple moving-average forecast from historical sales.

    Args:
        account_id: Account UUID.
        asin: Optional ASIN (aggregates all if omitted).
        horizon_days: Days to forecast ahead (default 30).
    """
    lookback = 90
    since = (date.today() - timedelta(days=lookback)).isoformat()
    asin_filter = "AND asin = :asin" if asin else ""
    params: dict = {"aid": account_id, "since": since}
    if asin:
        params["asin"] = asin

    async with get_session() as db:
        result = await db.execute(text(f"""
            SELECT date, SUM(ordered_product_sales) AS value
            FROM sales_data
            WHERE account_id = :aid AND date >= :since {asin_filter}
            GROUP BY date ORDER BY date
        """), params)
        rows = rows_to_list(result)

    if len(rows) < 7:
        return to_json({"error": "Not enough historical data (need at least 7 days)"})

    # Simple moving average forecast (14-day window)
    values = [float(r["value"]) for r in rows]
    window = min(14, len(values))
    ma = sum(values[-window:]) / window
    std = (sum((v - ma) ** 2 for v in values[-window:]) / window) ** 0.5

    predictions = []
    last_date = date.fromisoformat(str(rows[-1]["date"]))
    for i in range(1, horizon_days + 1):
        d = last_date + timedelta(days=i)
        noise = random.gauss(0, std * 0.1) if std > 0 else 0
        pred = max(0, ma + noise)
        predictions.append({
            "date": d.isoformat(),
            "value": round(pred, 2),
            "lower": round(max(0, pred - 1.96 * std), 2),
            "upper": round(pred + 1.96 * std, 2),
        })

    # Calculate MAPE on last 7 days as holdout
    holdout = values[-7:]
    pred_holdout = [ma] * len(holdout)
    mape = sum(
        abs(a - p) / a for a, p in zip(holdout, pred_holdout) if a > 0
    ) / max(len([a for a in holdout if a > 0]), 1) * 100
    rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(holdout, pred_holdout)) / len(holdout))

    return to_json({
        "account_id": account_id,
        "asin": asin,
        "horizon_days": horizon_days,
        "model_used": "simple_moving_average",
        "predictions": predictions,
        "mape": round(mape, 2),
        "rmse": round(rmse, 2),
        "historical_days": len(values),
    })


# ─── Export CSV ──────────────────────────────────────────────────────────────


@mcp.tool()
async def export_data_csv(
    data_type: str,
    start_date: str,
    end_date: str,
    account_id: str | None = None,
) -> str:
    """Export data as CSV text.

    Args:
        data_type: Type of data — sales, inventory, or products.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        account_id: Optional account UUID filter.
    """
    params: dict = {"start": start_date, "end": end_date}
    if account_id:
        acct_filter = "AND account_id = :aid"
        params["aid"] = account_id
    elif (ctx_ids := _get_context()["selected_account_ids"]):
        acct_filter = "AND account_id = ANY(:ctx_aids)"
        params["ctx_aids"] = ctx_ids
    else:
        acct_filter = ""

    queries = {
        "sales": f"""
            SELECT date, account_id, asin, sku, units_ordered,
                   ordered_product_sales, currency
            FROM sales_data
            WHERE date >= :start AND date <= :end {acct_filter}
            ORDER BY date, asin
        """,
        "inventory": f"""
            SELECT account_id, asin, sku, snapshot_date,
                   afn_fulfillable_quantity, afn_inbound_working_quantity,
                   afn_inbound_shipped_quantity, afn_reserved_quantity,
                   afn_total_quantity, mfn_fulfillable_quantity
            FROM inventory_data
            WHERE snapshot_date >= :start AND snapshot_date <= :end {acct_filter}
            ORDER BY snapshot_date, asin
        """,
        "products": f"""
            SELECT account_id, asin, sku, title, brand, category,
                   current_price, current_bsr, review_count, rating
            FROM products
            WHERE is_active = true {acct_filter}
            ORDER BY current_bsr ASC NULLS LAST
        """,
    }

    q = queries.get(data_type)
    if not q:
        return f"Invalid data_type '{data_type}'. Use: sales, inventory, or products."

    # For products, dates aren't used in the query — keep only account filter params
    if data_type == "products":
        p: dict = {}
        if account_id:
            p["aid"] = account_id
        elif "ctx_aids" in params:
            p["ctx_aids"] = params["ctx_aids"]
        params = p

    async with get_session() as db:
        result = await db.execute(text(q), params)
        rows = result.fetchall()

    if not rows:
        return "No data found for the given filters."

    columns = list(rows[0]._mapping.keys())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([str(v) if v is not None else "" for v in row])
    return buf.getvalue()


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
