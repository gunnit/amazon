"""Final prod E2E: streamed search terms, AI recommendations with product_signals, enriched endpoint."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")


def search_terms():
    from app.services.extraction_runner import run_brand_search_terms_sync_all

    try:
        print("search terms ->", run_brand_search_terms_sync_all(), flush=True)
    except Exception as exc:
        print("search terms FAILED:", str(exc)[:300], flush=True)


async def recommendations_and_endpoint():
    import httpx
    from sqlalchemy import select, text

    from app.core.security import create_access_token
    from app.db.session import AsyncSessionLocal
    from app.services.strategic_recommendations_service import StrategicRecommendationsService

    async with AsyncSessionLocal() as db:
        org_id = (await db.execute(text("SELECT organization_id FROM amazon_accounts LIMIT 1"))).scalar()
        user_id = (await db.execute(text(
            "SELECT user_id FROM organization_members WHERE organization_id = :o LIMIT 1"
        ), {"o": str(org_id)})).scalar()

        svc = StrategicRecommendationsService(db)
        try:
            recs = await svc.generate_for_organization(org_id, user_id=user_id, language="it")
            await db.commit()
            print(f"AI recommendations generated: {len(recs)}", flush=True)
            for r in recs[:6]:
                print(f"- [{r.category}/{r.priority}] {r.title}", flush=True)
                print(f"  {(r.rationale or '')[:220]}", flush=True)
        except Exception as exc:
            print("recommendations FAILED:", str(exc)[:300], flush=True)

        token = create_access_token({"sub": str(user_id)})
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.get(
                "https://inthezon-api.onrender.com/api/v1/analytics/per-product-performance",
                params={"start_date": "2026-05-13", "end_date": "2026-06-12", "limit": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            print("per-product endpoint:", resp.status_code, flush=True)
            if resp.status_code == 200:
                items = resp.json()["items"]
                enriched = [
                    i for i in items
                    if i.get("buy_box_owned") is not None
                    or i.get("net_margin_pct") is not None
                    or i.get("estimated_fees") is not None
                    or i.get("rating") is not None
                ]
                print(f"items: {len(items)}, with enrichment: {len(enriched)}", flush=True)
                for i in enriched[:4]:
                    print(json.dumps({k: i[k] for k in (
                        "asin", "rating", "review_count", "buy_box_owned",
                        "net_margin_pct", "amazon_fees", "estimated_fees", "margin_source")}), flush=True)


search_terms()
asyncio.run(recommendations_and_endpoint())
