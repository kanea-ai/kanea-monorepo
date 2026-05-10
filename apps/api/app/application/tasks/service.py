from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.auth.ports import MemberRepository
from app.application.notifications.service import NotificationService
from app.application.projects.ports import ProjectRepository
from app.application.tasks.ports import (
    TaskActivityRepository,
    TaskCommentRepository,
    TaskRatingRepository,
    TaskRelationRepository,
    TaskRepository,
    TaskRequestRepository,
    WorkspaceTaskSeqRepository,
)
from app.application.tasks.schemas import (
    ActivityResponse,
    CommentResponse,
    CreateCommentRequest,
    CreateRelationRequest,
    CreateRequestPayload,
    CreateTaskRequest,
    DelegateTaskRequest,
    FulfillRequestPayload,
    Principal,
    RateTaskRequest,
    RejectRequestPayload,
    RelationItem,
    SetBlockedRequest,
    TaskDetailResponse,
    TaskRatingResponse,
    TaskRelationsResponse,
    TaskRequestResponse,
    TaskResponse,
    UpdateTaskLinksRequest,
    UpdateTaskPriorityRequest,
    UpdateTaskStatusRequest,
)
from app.application.teams.ports import TeamRepository
from app.application.tenants.ports import WorkspaceReadRepository
from app.domain.entities import (
    Member,
    Task,
    TaskActivity,
    TaskComment,
    TaskRating,
    TaskRelation,
    TaskRequest,
)
from app.domain.enums import (
    MemberRole,
    RequestStatus,
    TaskActivityType,
    TaskRelationType,
    TaskStatus,
    TeamRole,
)
from app.domain.exceptions import (
    CrossTeamForbiddenError,
    DelegationForbiddenError,
    ProjectNotFoundError,
    RatingForbiddenError,
    TaskAlreadyRatedError,
    TaskNotFoundError,
    TaskNotInDoneStateError,
    TaskRelationAlreadyExistsError,
    TaskRelationNotFoundError,
    TaskRelationSelfLinkError,
    TaskRequestAlreadyResolvedError,
    TaskRequestForbiddenError,
    TaskRequestNotFoundError,
    TeamNotFoundError,
)

# Allowed status transitions. Any transition not listed here is rejected.
# Status transitions are intentionally unrestricted: the kanban
# spec lets users drag any card to any column, including reopening
# DONE / CANCELLED tasks (CANCELLED → PENDING is a common "we
# changed our mind" flow). The audit log still captures every
# transition so the trail is intact even when the lifecycle is
# non-linear. The orthogonal `is_blocked` flag remains separate —
# toggled via PATCH /tasks/{id}/block, never via status.


@dataclass(slots=True)
class TaskService:
    tasks: TaskRepository
    members: MemberRepository
    workspaces: WorkspaceReadRepository
    seq_allocator: WorkspaceTaskSeqRepository
    # Optional so existing call-sites that don't construct ratings (tests,
    # legacy DI paths) keep working. The rate_task() entry-point checks
    # for None and raises a clear error if it's invoked without one.
    ratings: TaskRatingRepository | None = None
    comments: TaskCommentRepository | None = None
    relations: TaskRelationRepository | None = None
    # Project / team lookups happen at create + move time so we can
    # 404 cross-tenant ids instead of letting the FK silently accept.
    projects: ProjectRepository | None = None
    team_lookup: TeamRepository | None = None
    # Append-only audit log for the AI history endpoints. Defensive:
    # all mutation paths no-op the recording if this isn't wired so
    # legacy DI / unit tests stay green.
    activities: TaskActivityRepository | None = None
    # Cross-team request workflow (section 3). Optional so legacy DI
    # paths that don't exercise the request endpoints stay valid.
    requests: TaskRequestRepository | None = None
    # Phase 4: drives @mention notifications on task creation +
    # comment posting. Optional so legacy tests that don't care
    # about notifications can omit it.
    notifications: NotificationService | None = None

    async def delegate(
        self,
        task_id: UUID,
        request: DelegateTaskRequest,
        requester: Principal,
    ) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        target = await self._load_target(request.member_id, requester)
        self._enforce_hierarchy(requester, target)

        updated = await self.tasks.assign(task_id=task.id, assignee_id=target.id)
        await self._record(
            task_id=task.id,
            actor=requester,
            event_type=TaskActivityType.DELEGATED,
            payload={
                "from": str(task.assignee_id) if task.assignee_id else None,
                "to": str(target.id),
            },
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def list_for_workspace(
        self,
        requester: Principal,
        *,
        status: TaskStatus | None = None,
        blocked_only: bool = False,
        project_id: UUID | None = None,
        team_id: UUID | None = None,
        assignee_id: UUID | None = None,
        priority_min: int | None = None,
        priority_max: int | None = None,
    ) -> list[TaskResponse]:
        """Workspace task list with RBAC. Workspace OWNER / ADMIN see
        all tasks and can filter freely; other principals are forced
        to see only their own assigned tasks regardless of any
        ?assignee_id query — the filter is silently overridden."""
        is_admin = requester.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN)
        effective_assignee_id = assignee_id if is_admin else requester.member_id

        rows = await self.tasks.list_by_workspace(
            requester.workspace_id,
            status=status,
            blocked_only=blocked_only,
            project_id=project_id,
            team_id=team_id,
            assignee_id=effective_assignee_id,
            priority_min=priority_min,
            priority_max=priority_max,
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return [TaskResponse.from_entity(row, prefix=prefix) for row in rows]

    async def get_by_id(self, task_id: UUID, requester: Principal) -> TaskDetailResponse:
        """Returns the task plus its full relation graph. Agents reading
        a task get the linked-work context (blocks / blocked_by / etc.)
        in a single round-trip; the standalone /relations endpoint is
        kept for callers that only want the buckets."""
        task = await self._load_task(task_id, requester)
        prefix = await self._workspace_prefix(requester.workspace_id)

        # Relations are best-effort: if the relations repo isn't wired
        # (legacy DI), fall back to an empty grouping rather than 500.
        if self.relations is not None:
            rows = await self.relations.list_for_task(task.id)
            grouped = await self._group_relations(task.id, rows, requester)
        else:
            grouped = TaskRelationsResponse(
                blocks=[],
                blocked_by=[],
                mitigates=[],
                mitigated_by=[],
                duplicates=[],
                duplicated_by=[],
                relates_to=[],
            )

        return TaskDetailResponse(
            id=task.id,
            workspace_id=task.workspace_id,
            created_by_id=task.created_by_id,
            title=task.title,
            status=task.status,
            priority=task.priority,
            seq=task.seq,
            public_id=f"{prefix}-{task.seq:03d}" if task.seq else f"{prefix}-000",
            description=task.description,
            assignee_id=task.assignee_id,
            project_id=task.project_id,
            team_id=task.team_id,
            due_at=task.due_at,
            is_blocked=task.is_blocked,
            blocked_reason=task.blocked_reason,
            created_at=task.created_at,
            updated_at=task.updated_at,
            relations=grouped,
        )

    async def create(self, request: CreateTaskRequest, requester: Principal) -> TaskResponse:
        # If an assignee is supplied, it must belong to the same workspace.
        if request.assignee_id is not None:
            assignee = await self.members.get_by_id(request.assignee_id)
            if assignee is None or assignee.workspace_id != requester.workspace_id:
                raise TaskNotFoundError("assignee not found")

        # Same-workspace check for project + team. We surface
        # ProjectNotFoundError / TeamNotFoundError on cross-tenant ids
        # rather than a generic TaskNotFoundError so the route can map
        # them precisely (and the agent's error log reads sensibly).
        if request.project_id is not None:
            await self._require_workspace_project(request.project_id, requester)
        if request.team_id is not None:
            await self._require_workspace_team(request.team_id, requester)
            await self._enforce_cross_team_rule(requester, request.team_id)

        # Atomic seq + prefix in one round-trip — rules out race-driven
        # collisions on the (workspace_id, seq) unique index.
        seq, prefix = await self.seq_allocator.allocate_next_task_seq(requester.workspace_id)

        now = datetime.utcnow()
        created = await self.tasks.create(
            Task(
                id=uuid4(),
                workspace_id=requester.workspace_id,
                created_by_id=requester.member_id,
                title=request.title,
                status=TaskStatus.PENDING,
                priority=request.priority,
                seq=seq,
                description=request.description,
                assignee_id=request.assignee_id,
                project_id=request.project_id,
                team_id=request.team_id,
                due_at=request.due_at,
                is_blocked=False,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        await self._record(
            task_id=created.id,
            actor=requester,
            event_type=TaskActivityType.CREATED,
            payload={"title": created.title},
        )
        # Phase 4 mentions: scan the description for @handles and notify.
        # Best-effort — if the notification service isn't wired (legacy
        # tests, stripped-down DI) we silently skip.
        if self.notifications is not None and created.description:
            await self.notifications.notify_mentions_in_task(
                body=created.description,
                task_id=created.id,
                actor=requester,
            )
        return TaskResponse.from_entity(created, prefix=prefix)

    async def update_links(
        self,
        task_id: UUID,
        request: UpdateTaskLinksRequest,
        requester: Principal,
    ) -> TaskResponse:
        """Move a task between projects and/or teams. Setting either to
        null explicitly clears it; omitting the field leaves it
        untouched (Pydantic's `model_fields_set` disambiguates)."""
        task = await self._load_task(task_id, requester)

        clear_project = "project_id" in request.model_fields_set and request.project_id is None
        clear_team = "team_id" in request.model_fields_set and request.team_id is None

        if request.project_id is not None and not clear_project:
            await self._require_workspace_project(request.project_id, requester)
        if request.team_id is not None and not clear_team:
            await self._require_workspace_team(request.team_id, requester)
            # Section 3: moving a task into another team needs the
            # same RBAC as creating one there.
            await self._enforce_cross_team_rule(requester, request.team_id)

        updated = await self.tasks.update_links(
            task.id,
            project_id=request.project_id if not clear_project else None,
            team_id=request.team_id if not clear_team else None,
            clear_project=clear_project,
            clear_team=clear_team,
        )

        # Record one event per dimension that actually changed. Either
        # field omitted from the request leaves it untouched and emits
        # nothing.
        if "project_id" in request.model_fields_set and updated.project_id != task.project_id:
            await self._record(
                task_id=task.id,
                actor=requester,
                event_type=TaskActivityType.PROJECT_CHANGED,
                payload={
                    "from": str(task.project_id) if task.project_id else None,
                    "to": str(updated.project_id) if updated.project_id else None,
                },
            )
        if "team_id" in request.model_fields_set and updated.team_id != task.team_id:
            await self._record(
                task_id=task.id,
                actor=requester,
                event_type=TaskActivityType.TEAM_CHANGED,
                payload={
                    "from": str(task.team_id) if task.team_id else None,
                    "to": str(updated.team_id) if updated.team_id else None,
                },
            )

        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def _record(
        self,
        *,
        task_id: UUID,
        actor: Principal | None,
        event_type: TaskActivityType,
        payload: dict | None = None,
    ) -> None:
        """Append an immutable audit-log row. Best-effort: if the
        activity repo isn't wired (legacy DI / unit tests), silently
        skip — the mutation it accompanies has already succeeded."""
        if self.activities is None:
            return
        await self.activities.create(
            TaskActivity(
                id=uuid4(),
                task_id=task_id,
                actor_member_id=actor.member_id if actor is not None else None,
                event_type=event_type,
                payload=payload or {},
            )
        )

    async def list_activity(self, task_id: UUID, requester: Principal) -> list[ActivityResponse]:
        if self.activities is None:  # pragma: no cover - DI invariant
            raise RuntimeError("list_activity called without activities repo")
        await self._load_task(task_id, requester)
        rows = await self.activities.list_for_task(task_id)
        return [await self._activity_to_response(r) for r in rows]

    async def _activity_to_response(self, row: TaskActivity) -> ActivityResponse:
        actor_name: str | None = None
        if row.actor_member_id is not None:
            actor = await self.members.get_by_id(row.actor_member_id)
            actor_name = actor.name if actor is not None else None
        return ActivityResponse(
            id=row.id,
            task_id=row.task_id,
            actor_member_id=row.actor_member_id,
            actor_name=actor_name,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
        )

    # ---------- cross-team requests (section 3) ----------

    async def create_request(
        self,
        task_id: UUID,
        request: CreateRequestPayload,
        requester: Principal,
    ) -> TaskRequestResponse:
        """File a cross-team request anchored to a source task.

        Auto-fulfilling: the target team task is minted immediately
        and a directed relation links source ↔ target (default
        BLOCKS). The request row is stored as FULFILLED so the team
        leadership inbox still surfaces the new arrival, but no
        approval step is required. This lets a USER raise cross-team
        work without ever needing access to the target team's board.

        RBAC: workspace admin OR the requester must own the source
        task (creator/assignee).
        """
        if self.requests is None or self.relations is None:  # pragma: no cover
            raise RuntimeError("requests / relations repo not wired")

        task = await self._load_task(task_id, requester)
        await self._require_workspace_team(request.requested_team_id, requester)

        is_admin = requester.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN)
        if not is_admin and requester.member_id not in (
            task.assignee_id,
            task.created_by_id,
        ):
            raise TaskRequestForbiddenError(
                "only the task assignee or creator may file a cross-team request"
            )

        # Mint the target task immediately. Allocate a workspace seq
        # so the new task gets a public id, and inherit the project
        # link from the source — cross-team work usually belongs to
        # the same product initiative.
        seq, _prefix = await self.seq_allocator.allocate_next_task_seq(requester.workspace_id)
        now = datetime.utcnow()
        target = await self.tasks.create(
            Task(
                id=uuid4(),
                workspace_id=requester.workspace_id,
                created_by_id=requester.member_id,
                title=request.suggested_title,
                status=TaskStatus.PENDING,
                priority=0,
                seq=seq,
                description=request.suggested_description,
                assignee_id=None,
                project_id=task.project_id,
                team_id=request.requested_team_id,
                due_at=None,
                is_blocked=False,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        await self._record(
            task_id=target.id,
            actor=requester,
            event_type=TaskActivityType.CREATED,
            payload={"title": target.title, "via_request_for_task_id": str(task.id)},
        )

        # Link source ↔ target with the requester's chosen relation.
        # The default BLOCKS preserves the previous semantics (target
        # blocks source) so existing UI behaviour around the
        # exception queue / blocked count stays consistent.
        await self.relations.create(
            TaskRelation(
                id=uuid4(),
                source_task_id=target.id,
                target_task_id=task.id,
                relation_type=request.relation_type,
            )
        )
        if request.relation_type is TaskRelationType.BLOCKS:
            await self._record(
                task_id=task.id,
                actor=requester,
                event_type=TaskActivityType.BLOCKED,
                payload={"blocked_by_task_id": str(target.id)},
            )

        # Record the request as FULFILLED on creation. The inbox
        # endpoint still picks it up so leadership has a notification
        # surface; rejecting an already-fulfilled request is a no-op
        # at the lifecycle layer.
        created = await self.requests.create(
            TaskRequest(
                id=uuid4(),
                source_task_id=task.id,
                requested_team_id=request.requested_team_id,
                requester_member_id=requester.member_id,
                suggested_title=request.suggested_title,
                suggested_description=request.suggested_description,
                justification=request.justification,
                status=RequestStatus.FULFILLED,
                fulfilled_task_id=target.id,
                resolver_member_id=requester.member_id,
                resolved_at=now,
            )
        )
        return await self._request_to_response(created)

    async def list_requests_for_task(
        self, task_id: UUID, requester: Principal
    ) -> list[TaskRequestResponse]:
        if self.requests is None:  # pragma: no cover - DI invariant
            raise RuntimeError("requests repo not wired")
        await self._load_task(task_id, requester)
        rows = await self.requests.list_for_task(task_id)
        return [await self._request_to_response(r) for r in rows]

    async def list_requests_for_team_inbox(
        self,
        team_id: UUID,
        requester: Principal,
        *,
        status_filter: RequestStatus | None = None,
    ) -> list[TaskRequestResponse]:
        """Leadership inbox: requests filed against tasks living on
        this team. Anyone in the workspace can read."""
        if self.requests is None:  # pragma: no cover - DI invariant
            raise RuntimeError("requests repo not wired")
        await self._require_workspace_team(team_id, requester)
        rows = await self.requests.list_for_source_team(team_id, status=status_filter)
        return [await self._request_to_response(r) for r in rows]

    async def fulfill_request(
        self,
        request_id: UUID,
        payload: FulfillRequestPayload,
        requester: Principal,
    ) -> TaskRequestResponse:
        """A MANAGER / LEAD on the source task's team mints the
        target task on requested_team_id and links the source via
        BLOCKS. The request flips to FULFILLED."""
        if self.requests is None or self.relations is None:  # pragma: no cover
            raise RuntimeError("requests / relations repo not wired")

        request_row = await self._load_workspace_request(request_id, requester)
        if request_row.status is not RequestStatus.PENDING:
            raise TaskRequestAlreadyResolvedError("request has already been resolved")
        if request_row.requested_team_id is None:
            raise TaskRequestForbiddenError(
                "the requested team has been deleted; reject this request"
            )

        source = await self.tasks.get_by_id(request_row.source_task_id)
        if source is None:  # pragma: no cover - FK guarantees this
            raise TaskNotFoundError("source task not found")

        await self._require_team_leadership_for_source(requester, source)

        # Mint the target task. Re-uses the standard create flow so
        # seq + activity recording happens. We bypass the cross-team
        # rule by routing through the repo directly with admin-equiv
        # validation (the leadership has already been verified).
        seq, prefix = await self.seq_allocator.allocate_next_task_seq(requester.workspace_id)

        title = payload.title or request_row.suggested_title
        description = (
            payload.description
            if payload.description is not None
            else request_row.suggested_description
        )

        if payload.assignee_id is not None:
            assignee = await self.members.get_by_id(payload.assignee_id)
            if assignee is None or assignee.workspace_id != requester.workspace_id:
                raise TaskNotFoundError("assignee not found")

        now = datetime.utcnow()
        target = await self.tasks.create(
            Task(
                id=uuid4(),
                workspace_id=requester.workspace_id,
                created_by_id=requester.member_id,
                title=title,
                status=TaskStatus.PENDING,
                priority=payload.priority,
                seq=seq,
                description=description,
                assignee_id=payload.assignee_id,
                project_id=source.project_id,  # inherit project from source
                team_id=request_row.requested_team_id,
                due_at=None,
                is_blocked=False,
                blocked_reason=None,
                created_at=now,
                updated_at=now,
            )
        )
        await self._record(
            task_id=target.id,
            actor=requester,
            event_type=TaskActivityType.CREATED,
            payload={
                "title": target.title,
                "via_request_id": str(request_row.id),
            },
        )

        # Link: target task BLOCKS source task. From the source's
        # perspective, source.blocked_by includes this new target.
        await self.relations.create(
            TaskRelation(
                id=uuid4(),
                source_task_id=target.id,
                target_task_id=source.id,
                relation_type=TaskRelationType.BLOCKS,
            )
        )
        # And the source picks up an audit-log row noting the block.
        await self._record(
            task_id=source.id,
            actor=requester,
            event_type=TaskActivityType.BLOCKED,
            payload={
                "via_request_id": str(request_row.id),
                "blocked_by_task_id": str(target.id),
            },
        )

        updated = await self.requests.mark_fulfilled(
            request_row.id,
            fulfilled_task_id=target.id,
            resolver_member_id=requester.member_id,
            resolved_at=now,
        )
        return await self._request_to_response(updated)

    async def reject_request(
        self,
        request_id: UUID,
        payload: RejectRequestPayload,
        requester: Principal,
    ) -> TaskRequestResponse:
        if self.requests is None:  # pragma: no cover - DI invariant
            raise RuntimeError("requests repo not wired")

        request_row = await self._load_workspace_request(request_id, requester)
        if request_row.status is not RequestStatus.PENDING:
            raise TaskRequestAlreadyResolvedError("request has already been resolved")

        source = await self.tasks.get_by_id(request_row.source_task_id)
        if source is None:  # pragma: no cover
            raise TaskNotFoundError("source task not found")
        await self._require_team_leadership_for_source(requester, source)

        now = datetime.utcnow()
        updated = await self.requests.mark_rejected(
            request_row.id,
            reason=payload.reason,
            resolver_member_id=requester.member_id,
            resolved_at=now,
        )
        return await self._request_to_response(updated)

    async def _load_workspace_request(self, request_id: UUID, requester: Principal) -> TaskRequest:
        if self.requests is None:  # pragma: no cover - DI invariant
            raise RuntimeError("requests repo not wired")
        request = await self.requests.get_by_id(request_id)
        if request is None:
            raise TaskRequestNotFoundError("request not found")
        # Tenant isolation: load the source task and 404 if it isn't
        # in the requester's workspace.
        source = await self.tasks.get_by_id(request.source_task_id)
        if source is None or source.workspace_id != requester.workspace_id:
            raise TaskRequestNotFoundError("request not found")
        return request

    async def _require_team_leadership_for_source(self, requester: Principal, source: Task) -> None:
        """Fulfill / reject permission: workspace admin OR a HEAD /
        MANAGER / LEAD on the source task's team."""
        if requester.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            return
        me = await self.members.get_by_id(requester.member_id)
        if me is None:  # pragma: no cover
            raise TaskRequestForbiddenError("requester not found")
        if (
            source.team_id is not None
            and me.team_id == source.team_id
            and me.team_role in (TeamRole.HEAD, TeamRole.MANAGER, TeamRole.LEAD)
        ):
            return
        raise TaskRequestForbiddenError(
            "only the source team's leadership (HEAD / MANAGER / LEAD) "
            "or a workspace admin can resolve this request"
        )

    async def _request_to_response(self, row: TaskRequest) -> TaskRequestResponse:
        requester_name: str | None = None
        resolver_name: str | None = None
        if row.requester_member_id is not None:
            r = await self.members.get_by_id(row.requester_member_id)
            requester_name = r.name if r is not None else None
        if row.resolver_member_id is not None:
            r = await self.members.get_by_id(row.resolver_member_id)
            resolver_name = r.name if r is not None else None
        return TaskRequestResponse(
            id=row.id,
            source_task_id=row.source_task_id,
            requested_team_id=row.requested_team_id,
            requester_member_id=row.requester_member_id,
            requester_name=requester_name,
            suggested_title=row.suggested_title,
            suggested_description=row.suggested_description,
            justification=row.justification,
            status=row.status,
            fulfilled_task_id=row.fulfilled_task_id,
            reject_reason=row.reject_reason,
            resolver_member_id=row.resolver_member_id,
            resolver_name=resolver_name,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )

    async def _enforce_cross_team_rule(self, requester: Principal, target_team_id: UUID) -> None:
        """Section 3: standard MEMBERs can't create tasks on a team
        they don't belong to. Workspace OWNER / ADMIN bypass; team
        leadership (HEAD / MANAGER / LEAD) bypass — they're the
        escalation path for the cross-team request workflow."""
        # Workspace admins always get through.
        if requester.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            return

        me = await self.members.get_by_id(requester.member_id)
        if me is None:
            # Defensive — JWT principal that doesn't resolve to a member
            # is a tenant-isolation issue we should never see.
            raise CrossTeamForbiddenError("requester not found in workspace")

        # Same-team writes are fine.
        if me.team_id == target_team_id:
            return

        # Leadership ranks can route work across teams.
        if me.team_role in (TeamRole.HEAD, TeamRole.MANAGER, TeamRole.LEAD):
            return

        raise CrossTeamForbiddenError(
            "MEMBERs can only create tasks on their own team — "
            "use the cross-team request flow to ask another team for help"
        )

    async def _require_workspace_project(self, project_id: UUID, requester: Principal) -> None:
        if self.projects is None:  # pragma: no cover - DI invariant
            raise RuntimeError("project repo not wired")
        project = await self.projects.get_by_id(project_id)
        if project is None or project.workspace_id != requester.workspace_id:
            raise ProjectNotFoundError("project not found")

    async def _require_workspace_team(self, team_id: UUID, requester: Principal) -> None:
        if self.team_lookup is None:  # pragma: no cover - DI invariant
            raise RuntimeError("team repo not wired")
        team = await self.team_lookup.get_by_id(team_id)
        if team is None or team.workspace_id != requester.workspace_id:
            raise TeamNotFoundError("team not found")

    async def update_status(
        self,
        task_id: UUID,
        request: UpdateTaskStatusRequest,
        requester: Principal,
    ) -> TaskResponse:
        task = await self._load_task(task_id, requester)
        # Same-status writes are no-ops — drag-and-drop sometimes fires
        # a status update on a card the user only nudged. Skipping
        # keeps the audit log tidy.
        if request.status is task.status:
            prefix = await self._workspace_prefix(requester.workspace_id)
            return TaskResponse.from_entity(task, prefix=prefix)

        updated = await self.tasks.update_status(
            task_id=task.id,
            status=request.status,
            tokens_used=request.tokens_used,
        )
        await self._record(
            task_id=task.id,
            actor=requester,
            event_type=TaskActivityType.STATUS_CHANGED,
            payload={"from": task.status.value, "to": request.status.value},
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def update_priority(
        self,
        task_id: UUID,
        request: UpdateTaskPriorityRequest,
        requester: Principal,
    ) -> TaskResponse:
        """Phase 4: edit task priority. Allowed when the principal is
        a workspace OWNER / ADMIN, or a team HEAD / MANAGER on the
        task's team. Plain MEMBERs (and LEADs, who can re-delegate but
        don't set scheduling priority) are denied."""
        task = await self._load_task(task_id, requester)
        if task.priority == request.priority:
            prefix = await self._workspace_prefix(requester.workspace_id)
            return TaskResponse.from_entity(task, prefix=prefix)

        await self._require_priority_editor(requester, task)

        updated = await self.tasks.update_priority(task.id, request.priority)
        await self._record(
            task_id=task.id,
            actor=requester,
            event_type=TaskActivityType.PRIORITY_CHANGED,
            payload={"from": task.priority, "to": request.priority},
        )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def _require_priority_editor(self, requester: Principal, task: Task) -> None:
        if requester.role in (MemberRole.WORKSPACE_OWNER, MemberRole.WORKSPACE_ADMIN):
            return
        me = await self.members.get_by_id(requester.member_id)
        if (
            me is not None
            and task.team_id is not None
            and me.team_id == task.team_id
            and me.team_role in (TeamRole.HEAD, TeamRole.MANAGER)
        ):
            return
        raise CrossTeamForbiddenError(
            "only workspace admins/owners or the task's team head/manager " "can change priority"
        )

    async def set_blocked(
        self,
        task_id: UUID,
        request: SetBlockedRequest,
        requester: Principal,
    ) -> TaskResponse:
        """Toggle the orthogonal blocked flag. The status is untouched —
        a blocked task can still be PENDING or IN_PROGRESS."""
        task = await self._load_task(task_id, requester)
        # When marking blocked, a reason is conventional. Empty string
        # is treated as None to keep the column tidy.
        reason = (request.reason or "").strip() or None if request.is_blocked else None
        updated = await self.tasks.set_blocked(
            task_id=task.id,
            is_blocked=request.is_blocked,
            blocked_reason=reason,
        )
        # The audit log distinguishes BLOCKED / UNBLOCKED so the agent
        # can build a clean blocked-time histogram per task.
        if request.is_blocked:
            await self._record(
                task_id=task.id,
                actor=requester,
                event_type=TaskActivityType.BLOCKED,
                payload={"reason": reason} if reason else {},
            )
        else:
            await self._record(
                task_id=task.id,
                actor=requester,
                event_type=TaskActivityType.UNBLOCKED,
            )
        prefix = await self._workspace_prefix(requester.workspace_id)
        return TaskResponse.from_entity(updated, prefix=prefix)

    async def rate_task(
        self,
        task_id: UUID,
        request: RateTaskRequest,
        requester: Principal,
    ) -> TaskRatingResponse:
        """Issuer-only post-completion rating. Score backs the
        accuracy_percent stat on the assignee's agent dashboard."""
        if self.ratings is None:  # pragma: no cover - DI invariant
            raise RuntimeError("rate_task called without a ratings repository")

        task = await self._load_task(task_id, requester)

        if task.created_by_id != requester.member_id:
            raise RatingForbiddenError("only the task creator can rate the work")
        if task.status is not TaskStatus.DONE:
            raise TaskNotInDoneStateError("task must be DONE before it can be rated")
        if await self.ratings.get_for_task(task.id) is not None:
            raise TaskAlreadyRatedError("task already rated; ratings are single-shot")

        rating = await self.ratings.create(
            TaskRating(
                id=uuid4(),
                task_id=task.id,
                rated_by_id=requester.member_id,
                rated_member_id=task.assignee_id,
                score=request.score,
                feedback=request.feedback,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await self._record(
            task_id=task.id,
            actor=requester,
            event_type=TaskActivityType.RATED,
            payload={"score": rating.score, "feedback": rating.feedback},
        )
        return TaskRatingResponse(
            task_id=rating.task_id,
            rated_by_id=rating.rated_by_id,
            rated_member_id=rating.rated_member_id,
            score=rating.score,
            feedback=rating.feedback,
            created_at=rating.created_at,
        )

    async def list_comments(self, task_id: UUID, requester: Principal) -> list[CommentResponse]:
        if self.comments is None:  # pragma: no cover - DI invariant
            raise RuntimeError("list_comments called without a comments repository")

        await self._load_task(task_id, requester)
        rows = await self.comments.list_for_task(task_id)
        return [await self._comment_to_response(row) for row in rows]

    async def post_comment(
        self,
        task_id: UUID,
        request: CreateCommentRequest,
        requester: Principal,
    ) -> CommentResponse:
        """Anyone in the workspace can comment — agents included. The
        author is whoever the JWT belongs to."""
        if self.comments is None:  # pragma: no cover - DI invariant
            raise RuntimeError("post_comment called without a comments repository")

        await self._load_task(task_id, requester)
        comment = await self.comments.create(
            TaskComment(
                id=uuid4(),
                task_id=task_id,
                author_member_id=requester.member_id,
                body=request.body,
            )
        )
        # Phase 4 mentions on comments. Self-mentions are skipped at
        # the NotificationService layer.
        if self.notifications is not None:
            await self.notifications.notify_mentions_in_comment(
                body=comment.body,
                task_id=task_id,
                comment_id=comment.id,
                actor=requester,
            )
        return await self._comment_to_response(comment)

    # ---------- relations ----------

    async def list_relations(self, task_id: UUID, requester: Principal) -> TaskRelationsResponse:
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("list_relations called without a relations repository")

        await self._load_task(task_id, requester)
        rows = await self.relations.list_for_task(task_id)
        return await self._group_relations(task_id, rows, requester)

    async def create_relation(
        self,
        task_id: UUID,
        request: CreateRelationRequest,
        requester: Principal,
    ) -> TaskRelation:
        """Idempotent: returns the existing row if (source, target,
        type) is already linked. Same-workspace required, no self-link."""
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("create_relation called without a relations repository")

        if task_id == request.target_task_id:
            raise TaskRelationSelfLinkError("a task cannot be linked to itself")

        # Both ends must be in the requester's workspace; both 404 the
        # same way as a missing task.
        await self._load_task(task_id, requester)
        await self._load_task(request.target_task_id, requester)

        existing = await self.relations.get_existing(
            source_task_id=task_id,
            target_task_id=request.target_task_id,
            relation_type=request.relation_type,
        )
        if existing is not None:
            raise TaskRelationAlreadyExistsError("this relation already exists between these tasks")

        return await self.relations.create(
            TaskRelation(
                id=uuid4(),
                source_task_id=task_id,
                target_task_id=request.target_task_id,
                relation_type=request.relation_type,
            )
        )

    async def delete_relation(self, task_id: UUID, relation_id: UUID, requester: Principal) -> None:
        """Removes the row by id. The route's task_id is taken as the
        owning task — we 404 if the relation isn't anchored to it."""
        if self.relations is None:  # pragma: no cover - DI invariant
            raise RuntimeError("delete_relation called without a relations repository")

        relation = await self.relations.get_by_id(relation_id)
        if relation is None:
            raise TaskRelationNotFoundError("relation not found")
        if task_id not in (relation.source_task_id, relation.target_task_id):
            raise TaskRelationNotFoundError("relation not found")
        # Tenant-isolation: the route already loaded the task to confirm
        # the requester has access; we trust task_id here.
        await self._load_task(task_id, requester)
        await self.relations.delete(relation_id)

    async def _group_relations(
        self,
        task_id: UUID,
        rows: list[TaskRelation],
        requester: Principal,
    ) -> TaskRelationsResponse:
        # Bulk-fetch the counterpart tasks in one round-trip so the UI
        # can render public_id + title without N additional GETs.
        counterpart_ids = {
            r.target_task_id if r.source_task_id == task_id else r.source_task_id for r in rows
        }
        tasks_by_id: dict[UUID, Task] = {}
        if counterpart_ids:
            for task in await self.tasks.list_by_ids(list(counterpart_ids)):
                # Defensive: only surface counterpart tasks in the same
                # workspace. Cross-workspace shouldn't be possible
                # because creation rejects it, but DB-level FKs don't
                # enforce tenancy so we double-check here.
                if task.workspace_id == requester.workspace_id:
                    tasks_by_id[task.id] = task

        prefix = await self._workspace_prefix(requester.workspace_id)

        def to_item(relation: TaskRelation, counterpart_id: UUID) -> RelationItem | None:
            counterpart = tasks_by_id.get(counterpart_id)
            if counterpart is None:
                return None
            return RelationItem(
                relation_id=relation.id,
                task_id=counterpart.id,
                public_id=f"{prefix}-{counterpart.seq:03d}",
                title=counterpart.title,
                status=counterpart.status,
                is_blocked=counterpart.is_blocked,
            )

        groups: dict[str, list[RelationItem]] = {
            "blocks": [],
            "blocked_by": [],
            "mitigates": [],
            "mitigated_by": [],
            "duplicates": [],
            "duplicated_by": [],
            "relates_to": [],
        }

        for r in rows:
            outgoing = r.source_task_id == task_id
            counterpart_id = r.target_task_id if outgoing else r.source_task_id
            item = to_item(r, counterpart_id)
            if item is None:
                continue

            if r.relation_type is TaskRelationType.RELATES_TO:
                # Symmetric — the same row appears in `relates_to` for
                # both ends; don't double-bucket.
                groups["relates_to"].append(item)
                continue

            if r.relation_type is TaskRelationType.BLOCKS:
                (groups["blocks"] if outgoing else groups["blocked_by"]).append(item)
            elif r.relation_type is TaskRelationType.MITIGATES:
                (groups["mitigates"] if outgoing else groups["mitigated_by"]).append(item)
            elif r.relation_type is TaskRelationType.DUPLICATES:
                (groups["duplicates"] if outgoing else groups["duplicated_by"]).append(item)

        return TaskRelationsResponse(**groups)

    async def _comment_to_response(self, comment: TaskComment) -> CommentResponse:
        author_name: str | None = None
        if comment.author_member_id is not None:
            # Best-effort name lookup. `members` is the auth-shape repo
            # so this is a single primary-key fetch per comment. Lists
            # of comments are paginated in practice; for now they're
            # rendered in full.
            author = await self.members.get_by_id(comment.author_member_id)
            author_name = author.name if author is not None else None
        return CommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            author_member_id=comment.author_member_id,
            author_name=author_name,
            body=comment.body,
            created_at=comment.created_at,
        )

    async def _load_task(self, task_id: UUID, requester: Principal) -> Task:
        task = await self.tasks.get_by_id(task_id)
        if task is None or task.workspace_id != requester.workspace_id:
            raise TaskNotFoundError("task not found")
        return task

    async def _load_target(self, member_id: UUID, requester: Principal) -> Member:
        target = await self.members.get_by_id(member_id)
        if target is None or target.workspace_id != requester.workspace_id:
            raise TaskNotFoundError("assignee not found")
        return target

    async def _workspace_prefix(self, workspace_id: UUID) -> str:
        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:  # pragma: no cover - tenant invariant
            raise TaskNotFoundError("workspace not found")
        return ws.task_prefix

    @staticmethod
    def _enforce_hierarchy(requester: Principal, target: Member) -> None:
        # Lower numerical priority = higher rank. A requester may only delegate
        # to members with a strictly greater numerical priority (lower rank).
        if requester.priority >= target.priority:
            raise DelegationForbiddenError(
                "requester rank is not high enough to delegate to this member"
            )
