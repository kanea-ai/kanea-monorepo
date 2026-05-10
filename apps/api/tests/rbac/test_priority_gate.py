"""Tests for the priority-aware admin gate (require_admin_priority_le).

The Phase-6 RBAC matrix gates an admin's *reach* on top of their role:
- Department CRUD requires admin priority ≤ 2.
- Team CRUD requires admin priority ≤ 3.
- Owners always pass (their role overrides priority).
- USER role is rejected before priority is even considered.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import require_admin_priority_le
from app.application.tasks.schemas import Principal
from app.domain.enums import MemberRole, MemberType


def _principal(*, role: MemberRole, priority: int) -> Principal:
    return Principal(
        member_id=uuid4(),
        workspace_id=uuid4(),
        type=MemberType.HUMAN,
        priority=priority,
        scope="human",
        role=role,
    )


def _gate(max_priority: int):
    return require_admin_priority_le(max_priority)


def test_owner_always_passes_regardless_of_priority() -> None:
    gate = _gate(2)
    # Even an owner with a stale (high) priority value should pass —
    # owners aren't limited by the priority bar.
    assert gate(_principal(role=MemberRole.WORKSPACE_OWNER, priority=10)) is not None


def test_admin_with_priority_at_threshold_passes() -> None:
    gate = _gate(2)
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    assert gate(p).priority == 2


def test_admin_with_priority_below_threshold_passes() -> None:
    gate = _gate(3)
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=2)
    assert gate(p).priority == 2


def test_admin_with_priority_above_threshold_403s() -> None:
    gate = _gate(2)
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=3)
    with pytest.raises(HTTPException) as excinfo:
        gate(p)
    assert excinfo.value.status_code == 403
    assert "priority" in excinfo.value.detail.lower()


def test_user_role_rejected_before_priority() -> None:
    """A USER (formerly MEMBER) role gets the role-mismatch detail
    rather than the priority detail — the role check runs first."""
    gate = _gate(10)
    p = _principal(role=MemberRole.WORKSPACE_USER, priority=1)
    with pytest.raises(HTTPException) as excinfo:
        gate(p)
    assert excinfo.value.status_code == 403
    assert "owner or admin" in excinfo.value.detail.lower()


def test_department_reach_admin_at_priority_3_403s() -> None:
    """The pre-built DepartmentReachDep is priority ≤ 2. A P3 admin
    cannot manage departments."""
    gate = _gate(2)  # Same as DepartmentReachDep
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=3)
    with pytest.raises(HTTPException):
        gate(p)


def test_team_reach_admin_at_priority_3_passes() -> None:
    """The pre-built TeamReachDep is priority ≤ 3. A P3 admin can
    manage teams."""
    gate = _gate(3)
    p = _principal(role=MemberRole.WORKSPACE_ADMIN, priority=3)
    assert gate(p).priority == 3
