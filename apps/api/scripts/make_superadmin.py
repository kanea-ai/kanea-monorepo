"""Elevate a global User to platform superadmin.

This is the ONLY way ``users.is_superadmin`` gets flipped — there is
no API endpoint that mutates it, by design. Running the script
requires DB access (i.e. an operator on the machine), so a
compromised user account cannot bootstrap its own escalation.

Usage::

    cd apps/api
    poetry run python -m scripts.make_superadmin --email you@kanea.ai

By default the script refuses to demote a user (``--revoke`` is the
explicit opt-in). The DSN is read from ``settings.database_url`` so
local / staging / prod all work without env juggling.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.infrastructure.db.models import UserModel


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="make_superadmin",
        description="Set or revoke the platform superadmin flag on a global User.",
    )
    p.add_argument(
        "--email",
        required=True,
        help="The email address of the user to elevate. Must match the users.email row.",
    )
    p.add_argument(
        "--revoke",
        action="store_true",
        help="Set is_superadmin=False instead of True (explicit opt-in).",
    )
    return p


async def _run(email: str, *, revoke: bool) -> int:
    target_value = not revoke
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    try:
        async with engine.begin() as conn:
            # Look up the user first so we can give a useful message
            # for both "no such email" and "no-op" cases. Cheaper than
            # a blind UPDATE that returns 0 rows.
            row = (
                await conn.execute(
                    select(UserModel.id, UserModel.full_name, UserModel.is_superadmin).where(
                        UserModel.email == email
                    )
                )
            ).one_or_none()
            if row is None:
                print(f"[make_superadmin] no user found for email={email!r}", file=sys.stderr)
                return 2
            if row.is_superadmin == target_value:
                action = "already superadmin" if target_value else "already non-superadmin"
                print(f"[make_superadmin] {row.full_name} <{email}> is {action} — nothing to do.")
                return 0
            await conn.execute(
                update(UserModel).where(UserModel.email == email).values(is_superadmin=target_value)
            )
            verb = "elevated" if target_value else "revoked"
            print(f"[make_superadmin] {verb}: {row.full_name} <{email}>")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return asyncio.run(_run(args.email, revoke=args.revoke))


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
