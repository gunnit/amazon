"""Rename a single Amazon account by ID without touching its credentials.

Usage (from backend/ with the virtualenv active):

    python scripts/rename_amazon_account.py <account_id> "New client-facing name"

The script never reads or writes encrypted credential columns.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.amazon_account import AmazonAccount


async def _rename(account_id: UUID, new_name: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AmazonAccount).where(AmazonAccount.id == account_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            print(f"No account found with id {account_id}", file=sys.stderr)
            sys.exit(2)

        old_name = account.account_name
        if old_name == new_name:
            print(f"Account {account_id} is already named '{new_name}'.")
            return

        account.account_name = new_name
        await session.commit()
        print(f"Renamed account {account_id}: '{old_name}' -> '{new_name}'")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account_id", type=UUID, help="UUID of the AmazonAccount to rename")
    parser.add_argument("new_name", help="New client-facing account name")
    args = parser.parse_args()

    if not args.new_name.strip():
        parser.error("new_name must not be empty")

    asyncio.run(_rename(args.account_id, args.new_name.strip()))


if __name__ == "__main__":
    main()
