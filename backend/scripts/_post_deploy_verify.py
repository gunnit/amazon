"""Post-deploy: re-run ingestion with fixed parsers, verify signals on prod."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.user import Organization


def run_ingestion():
    from app.services.extraction_runner import (
        run_market_snapshot_all,
        run_asin_economics_sync_all,
        run_brand_search_terms_sync_all,
    )

    for fn in (run_market_snapshot_all, run_asin_economics_sync_all, run_brand_search_terms_sync_all):
        try:
            print(fn.__name__, "->", fn(), flush=True)
        except Exception as exc:
            print(fn.__name__, "FAILED:", str(exc)[:300], flush=True)


async def census():
    async with AsyncSessionLocal() as db:
        for t in ("fee_estimates", "price_snapshots", "asin_economics", "brand_search_terms"):
            n = (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
            print(f"{t}: {n} rows", flush=True)
        bb = (await db.execute(text(
            "SELECT is_buy_box_ours, COUNT(*) FROM price_snapshots GROUP BY 1"
        ))).all()
        print("buy box ownership:", {str(r[0]): r[1] for r in bb}, flush=True)

        org = (await db.execute(select(Organization))).scalars().first()
        from app.services.strategic_recommendations_service import StrategicRecommendationsService

        svc = StrategicRecommendationsService(db)
        snap = await svc._build_org_snapshot(org.id, 30)
        signals = snap.get("product_signals", {})
        print("product_signals blocks:", list(signals.keys()), flush=True)
        print(json.dumps(signals, default=str)[:1500], flush=True)


# The run_* wrappers each create their own event loop, so they must be invoked
# from plain sync code — never inside asyncio.run().
run_ingestion()
asyncio.run(census())
