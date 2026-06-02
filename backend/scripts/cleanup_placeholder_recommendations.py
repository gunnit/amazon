"""Delete strategic recommendations that leaked placeholder account names.

Older AI-generated recommendations referenced placeholder account names such as
"Real Account", "First Account" or "Second Account" in their title/rationale.
This script finds and removes those rows. Matching uses Postgres word boundaries
so it never trips on substrings like "really", "realistic" or "firstly".

Usage (from backend/ with the virtualenv active):

    python scripts/cleanup_placeholder_recommendations.py            # dry-run
    python scripts/cleanup_placeholder_recommendations.py --apply    # delete
    python scripts/cleanup_placeholder_recommendations.py --org-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

PLACEHOLDER_PATTERN = r"\y(real account|first account|second account|real|first|second)\y"


async def _cleanup(apply: bool, org_id: UUID | None) -> None:
    where = "(title ~* :pat OR rationale ~* :pat)"
    params: dict[str, object] = {"pat": PLACEHOLDER_PATTERN}
    if org_id is not None:
        where += " AND organization_id = :org_id"
        params["org_id"] = org_id

    async with AsyncSessionLocal() as session:
        total = (
            await session.execute(text("SELECT COUNT(*) FROM strategic_recommendations"))
        ).scalar_one()
        print(f"strategic_recommendations total rows: {total}")

        rows = (
            await session.execute(
                text(
                    f"SELECT id, status, title FROM strategic_recommendations WHERE {where}"
                ),
                params,
            )
        ).all()

        print(f"matched {len(rows)} placeholder row(s):")
        for row in rows:
            print(f"  {row.id} [{row.status}] {row.title}")

        if not apply:
            print("\nDRY-RUN: no rows deleted. Re-run with --apply to delete.")
            return

        if not rows:
            print("\nNothing to delete.")
            return

        result = await session.execute(
            text(f"DELETE FROM strategic_recommendations WHERE {where}"), params
        )
        await session.commit()
        print(f"\nDeleted {result.rowcount} row(s).")

        remaining = (
            await session.execute(text("SELECT COUNT(*) FROM strategic_recommendations"))
        ).scalar_one()
        print(f"strategic_recommendations total rows after delete: {remaining}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Delete matched rows (default is dry-run)"
    )
    parser.add_argument(
        "--org-id", type=UUID, default=None, help="Limit cleanup to a single organization"
    )
    args = parser.parse_args()

    asyncio.run(_cleanup(args.apply, args.org_id))


if __name__ == "__main__":
    main()
