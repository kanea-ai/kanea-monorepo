"""Guard against Postgres native-enum migration drift.

Several columns map to Postgres *native* enum types declared with
``create_type=False`` (see ``app/infrastructure/db/models.py``):
``member_type``, ``team_role``, ``project_status``,
``task_relation_type`` and ``notification_type``. Because
``create_type=False`` tells SQLAlchemy *not* to emit
``CREATE TYPE`` / ``ALTER TYPE`` from the model metadata, every value
of these enums must be introduced by an explicit Alembic migration
(``CREATE TYPE ... AS ENUM (...)`` for the first set, then
``ALTER TYPE ... ADD VALUE ...`` for each value added later).

A value added to the *Python* enum without a matching migration is a
production-only failure that the rest of the test suite cannot catch:
the integration harness (``tests/integration/conftest.py``) builds the
enum types from the model metadata via ``enum.create(checkfirst=True)``
— so in tests the enum always has every current value — while the
production database is built by the migrations alone. The two diverge
silently, and the first insert of the un-migrated value 500s in prod
with ``invalid input value for enum``.

This exact gap shipped once: ``NotificationType.CROSS_TEAM_REQUEST``
was added in code (the cross-team request feature) with no
``ALTER TYPE notification_type ADD VALUE`` migration, so every
cross-team request 500'd in production at the notification insert
while every test passed. This test is the structural guard that
closes the class: it fails the moment a native-enum value exists in
Python without a migration that introduces it.

The check is static (no database required) so it runs on every PR as
part of the unit suite, not only when an integration Postgres is
available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.enums import (
    MemberType,
    NotificationType,
    ProjectStatus,
    TaskRelationType,
    TeamRole,
)

# Map each Postgres native enum type name (as declared with
# ``create_type=False`` in models.py) to its backing Python enum.
NATIVE_ENUMS = {
    "member_type": MemberType,
    "team_role": TeamRole,
    "project_status": ProjectStatus,
    "task_relation_type": TaskRelationType,
    "notification_type": NotificationType,
}

_VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _migration_texts() -> list[str]:
    files = sorted(_VERSIONS_DIR.glob("*.py"))
    assert files, f"no migration files found under {_VERSIONS_DIR}"
    return [f.read_text(encoding="utf-8") for f in files]


@pytest.mark.parametrize("enum_name,enum_cls", list(NATIVE_ENUMS.items()))
def test_native_enum_values_are_introduced_by_a_migration(enum_name, enum_cls) -> None:
    """Every value of a ``create_type=False`` native enum must appear in
    a migration that references that enum's type name. Catches a Python
    enum value added without the required ``ALTER TYPE ... ADD VALUE``."""
    texts = _migration_texts()
    # Scope to the migrations that actually touch this enum type, so a
    # value-literal that happens to appear elsewhere can't mask a real
    # gap (and cross-enum literal collisions can't produce a false pass).
    scoped = "\n".join(t for t in texts if enum_name in t)
    assert scoped, f"no migration references the native enum type {enum_name!r}"

    missing = [
        member.value
        for member in enum_cls
        if f'"{member.value}"' not in scoped and f"'{member.value}'" not in scoped
    ]
    assert not missing, (
        f"native enum {enum_name!r} has Python value(s) {missing} with no "
        f"migration. {enum_name} is declared create_type=False, so each value "
        f"needs an explicit ALTER TYPE {enum_name} ADD VALUE migration — "
        f"otherwise the value inserts fine in tests (enum built from metadata) "
        f"but 500s in production (enum built from migrations)."
    )
