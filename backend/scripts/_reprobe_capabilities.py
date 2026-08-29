"""Force-refresh Brand Analysis capability probes for all accounts (persisted)."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount


async def main():
    from app.services.brand_analysis_capabilities import detect_brand_analysis_capabilities

    async with AsyncSessionLocal() as db:
        accounts = (await db.execute(select(AmazonAccount))).scalars().all()
        for account in accounts:
            if not account.sp_api_refresh_token_encrypted:
                print(f"{account.account_name}: no token, skipping", flush=True)
                continue
            res = await detect_brand_analysis_capabilities(db, account, force_refresh=True)
            await db.commit()
            green = [k for k, v in res.capabilities.items() if v]
            red = {k: res.last_error_by_capability.get(k, "") for k, v in res.capabilities.items() if not v}
            print(f"=== {account.account_name} ===", flush=True)
            print("GREEN:", ", ".join(sorted(green)) or "-", flush=True)
            print("RED:", json.dumps(red), flush=True)


asyncio.run(main())
