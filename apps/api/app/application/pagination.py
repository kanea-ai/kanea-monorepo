"""Shared paginated-response shape.

Every paginated list endpoint returns ``{items, total}`` where:

- ``items`` is the page slice the client asked for via ``skip`` /
  ``limit`` query params (or whatever pagination scheme the endpoint
  exposes).
- ``total`` is the *unfiltered* count of rows that match the
  request's filters — i.e. the size of the underlying result set
  before pagination is applied. Drives the page-number controls.

The shape is generic over the item type so each endpoint can declare
``response_model=Page[TeamResponse]`` etc. and the OpenAPI schema
nests the right item shape.

The Board view stays unpaginated by design (kanban needs the full
task graph) so this module is intentionally not reused by /tasks —
new paginated endpoints opt in.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# Default page size when a route doesn't pass ``limit`` explicitly.
# 25 matches what the FE renders by default; tuned so a single screen
# covers the typical workspace's table without paginating.
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict()

    items: list[T] = Field(default_factory=list)
    total: int = Field(ge=0)
