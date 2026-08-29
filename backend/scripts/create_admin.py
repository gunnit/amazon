"""Create the first organization and its first admin on an empty database.

Registration is closed, so there is no way to create the very first user from
the UI. This is that way in. Safe to run against a populated database: it
refuses to touch an email that already exists.

    python scripts/create_admin.py --email you@example.com --org "Acme"

The password is read from the ADMIN_PASSWORD environment variable, or prompted
for, so it never lands in shell history.
"""
import argparse
import asyncio
import os
import re
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import Organization, OrganizationMember, User, UserRole


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"


async def main(email: str, full_name: str, org_name: str, password: str) -> int:
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
            print(f"A user with email {email} already exists — nothing to do.")
            return 1

        slug = slugify(org_name)
        org = (
            await db.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        if org is None:
            org = Organization(name=org_name, slug=slug)
            db.add(org)
            await db.flush()
            print(f"Created organization {org.name} ({org.id})")
        else:
            print(f"Reusing existing organization {org.name} ({org.id})")

        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        db.add(
            OrganizationMember(
                user_id=user.id, organization_id=org.id, role=UserRole.ADMIN
            )
        )
        await db.commit()
        print(f"Created admin {user.email} ({user.id}) in {org.name}")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--org", required=True, help="Organization name")
    parser.add_argument("--name", default="", help="Full name of the admin")
    args = parser.parse_args()

    pwd = os.environ.get("ADMIN_PASSWORD") or getpass("Password for the new admin: ")
    if len(pwd) < 8:
        sys.exit("Password must be at least 8 characters.")

    sys.exit(asyncio.run(main(args.email, args.name or args.email, args.org, pwd)))
