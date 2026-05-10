"""Shared fixtures for task service tests.

TaskService gained two repos in batch 2 — workspace lookup (for the
public_id prefix) and a seq allocator. They're identical no-op mocks
across most tests, so we centralise them here. Individual tests can
still override them by re-declaring the fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.entities import Workspace


@pytest.fixture
def workspace_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = Workspace(
        id=uuid4(),
        name="Test",
        slug="test",
        task_prefix="TASK",
        next_task_seq=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return repo


@pytest.fixture
def seq_allocator() -> AsyncMock:
    repo = AsyncMock()
    repo.allocate_next_task_seq.return_value = (1, "TASK")
    return repo
