#!/usr/bin/env python
"""Operational CLI for the api.

Lets backend developers run privileged ops from the terminal without
hand-rolling SQL. Currently supports promoting a user's workspace
role; the structure (sub-commands) makes it easy to add more.

Usage:
    poetry run python manage.py promote-user alice@example.com
    poetry run python manage.py promote-user alice@example.com --role ADMIN

The DB connection comes from settings.database_url, same as the api.
Run from anywhere — the script changes working dir to apps/api so the
.env is found.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make sure `app.*` imports resolve when invoked from the repo root or
# from apps/api. We don't want to require activating a venv first.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.domain.enums import MemberRole  # noqa: E402
from app.infrastructure.db.models import MemberModel  # noqa: E402
from app.infrastructure.db.session import get_sessionmaker  # noqa: E402


async def promote_user(email: str, role: MemberRole) -> int:
    """Update the member's workspace role. Returns the process exit
    code (0 success, non-zero on error)."""
    async with get_sessionmaker()() as session:
        stmt = select(MemberModel).where(MemberModel.email == email)
        member = (await session.execute(stmt)).scalar_one_or_none()
        if member is None:
            print(f"error: no member with email {email!r}", file=sys.stderr)
            return 2
        if member.role is role:
            print(f"{email} is already {role.value} — no-op")
            return 0
        previous = member.role
        member.role = role
        await session.commit()
        print(f"{email}: {previous.value} -> {role.value}")
        return 0


def _parse_role(raw: str) -> MemberRole:
    raw = raw.upper()
    try:
        return MemberRole(raw)
    except ValueError as exc:
        valid = ", ".join(r.value for r in MemberRole)
        raise argparse.ArgumentTypeError(f"invalid role {raw!r}; pick one of {valid}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(prog="manage.py")
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser(
        "promote-user",
        help="Elevate a user's workspace role (OWNER / ADMIN).",
    )
    promote.add_argument("email", help="The member's email address.")
    promote.add_argument(
        "--role",
        type=_parse_role,
        default=MemberRole.WORKSPACE_OWNER,
        help="Target role (default: OWNER).",
    )

    args = parser.parse_args()

    if args.command == "promote-user":
        return asyncio.run(promote_user(args.email, args.role))

    parser.error(f"unknown command: {args.command}")
    return 1  # pragma: no cover - argparse exits before this


if __name__ == "__main__":
    sys.exit(main())
