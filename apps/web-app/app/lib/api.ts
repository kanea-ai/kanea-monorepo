// Thin fetch wrapper for the FastAPI backend.
//
// All paths are relative — the LB routes `/api/*` to the api Cloud Run service
// in production, and `next dev` proxies via the same path during local dev
// (with the api running on :8000 you can override with NEXT_PUBLIC_API_BASE_URL).
// Auth token lives in localStorage under `kanea_token`; api401 throws a typed
// error so callers can redirect to /login.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
const V1 = '/api/v1';

export const TOKEN_STORAGE_KEY = 'kanea_token';

// Standard paginated payload returned by every list endpoint that
// supports ``skip``/``limit``. ``items`` is the page slice; ``total``
// is the unfiltered count under the request's filters so the UI can
// render page-number controls. The Board (kanban) is intentionally
// unpaginated — it stays on the legacy ``T[]`` shape via
// tasksApi.list / useTasks.
export interface Page<T> {
  items: T[];
  total: number;
}

export interface PaginationOpts {
  skip?: number;
  limit?: number;
}

export const DEFAULT_PAGE_SIZE = 25;
// Mirrors app/application/pagination.MAX_PAGE_SIZE on the api so the
// frontend can fetch "all" rows for picker dropdowns (CreateTask team
// select, etc.) without the api rejecting a too-large limit.
export const MAX_PAGE_SIZE = 200;

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'IN_REVIEW' | 'DONE' | 'CANCELLED';

export interface Task {
  id: string;
  workspace_id: string;
  created_by_id: string;
  title: string;
  status: TaskStatus;
  priority: number;
  seq: number;
  // Human-readable id like ``DEVOPS-001``. Built server-side from the
  // workspace prefix + zero-padded seq.
  public_id: string;
  description: string | null;
  assignee_id: string | null;
  // Denormalised assignee display name (resolved server-side from
  // assignee_id). Null when the task is unassigned, or in the rare
  // legacy-data case where the FK didn't cascade (ON DELETE SET NULL
  // on the assignee column normally nulls assignee_id when the
  // member is deleted). Read this directly; don't try to resolve the
  // name from /tenants/members/{id}, which 403s for non-admin
  // cross-team lookups.
  assignee_name: string | null;
  // Workspace -> Project -> Task -> Team links. Both nullable: a
  // backlog task can live without a project, an unowned task without
  // a team. Server SET-NULLs them when the parent is deleted.
  project_id: string | null;
  team_id: string | null;
  due_at: string | null;
  // Blocked is orthogonal to status. A task can be PENDING/IN_PROGRESS
  // and blocked at the same time. The Kanban renders blocked cards
  // with a red border regardless of column.
  is_blocked: boolean;
  blocked_reason: string | null;
  created_at: string;
  updated_at: string;
}

// Returned by GET /tasks/{id}. Same shape as Task plus the seven
// relation buckets so agents (and the detail page) get the full
// linked-work graph in a single round-trip.
export interface TaskDetail extends Task {
  relations: TaskRelations;
}

export interface UpdateStatusPayload {
  status: TaskStatus;
  // Cumulative tokens spent on the task. Optional — agents pass it on
  // status updates so tokens roll up across iterations.
  tokens_used?: number | null;
}

export interface SetBlockedPayload {
  is_blocked: boolean;
  reason?: string | null;
}

export interface TaskComment {
  id: string;
  task_id: string;
  author_member_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface CreateCommentPayload {
  body: string;
}

export type RequestStatus = 'PENDING' | 'FULFILLED' | 'REJECTED';

export interface TaskRequest {
  id: string;
  source_task_id: string;
  requested_team_id: string | null;
  requester_member_id: string | null;
  requester_name: string | null;
  suggested_title: string;
  suggested_description: string | null;
  justification: string | null;
  status: RequestStatus;
  fulfilled_task_id: string | null;
  reject_reason: string | null;
  resolver_member_id: string | null;
  resolver_name: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface CreateRequestPayload {
  requested_team_id: string;
  suggested_title: string;
  suggested_description?: string | null;
  justification?: string | null;
}

export interface FulfillRequestPayload {
  title?: string | null;
  description?: string | null;
  priority?: number;
  assignee_id?: string | null;
}

export interface RejectRequestPayload {
  reason?: string | null;
}

export type TaskActivityType =
  | 'CREATED'
  | 'STATUS_CHANGED'
  | 'ASSIGNED'
  | 'DELEGATED'
  | 'BLOCKED'
  | 'UNBLOCKED'
  | 'PROJECT_CHANGED'
  | 'TEAM_CHANGED'
  | 'RATED';

export interface TaskActivity {
  id: string;
  task_id: string;
  actor_member_id: string | null;
  actor_name: string | null;
  event_type: TaskActivityType;
  // Free-form payload, shape depends on event_type. The web view
  // treats it as Record<string, unknown>; consumers that need stricter
  // typing should narrow on event_type.
  payload: Record<string, unknown>;
  created_at: string;
}

export type RelationType = 'BLOCKS' | 'MITIGATES' | 'DUPLICATES' | 'RELATES_TO';

export interface RelationItem {
  relation_id: string;
  task_id: string;
  public_id: string;
  title: string;
  status: TaskStatus;
  is_blocked: boolean;
}

export interface TaskRelations {
  blocks: RelationItem[];
  blocked_by: RelationItem[];
  mitigates: RelationItem[];
  mitigated_by: RelationItem[];
  duplicates: RelationItem[];
  duplicated_by: RelationItem[];
  relates_to: RelationItem[];
}

export interface CreateRelationPayload {
  relation_type: RelationType;
  target_task_id: string;
}

export interface CreateTaskPayload {
  title: string;
  description?: string | null;
  priority?: number;
  assignee_id?: string | null;
  project_id?: string | null;
  team_id?: string | null;
  due_at?: string | null;
}

export interface UpdateTaskLinksPayload {
  project_id?: string | null;
  team_id?: string | null;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  workspace_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// Login is branched in Phase 1: single-workspace users get a token
// straight away, multi-workspace users get a selection token + the
// list of workspaces they can pick from.
export interface WorkspaceOption {
  workspace_id: string;
  name: string;
  role: 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';
}

export interface LoginResponse {
  requires_selection: boolean;
  /** True when the caller is a brand-new SSO user — no User row exists
   *  yet. The FE must redirect to /onboarding/workspace and POST to
   *  /auth/complete-oauth-onboarding once a workspace name is chosen. */
  requires_onboarding: boolean;
  access_token: string | null;
  token_type: string;
  expires_in: number | null;
  selection_token: string | null;
  workspaces: WorkspaceOption[] | null;
  /** Short-lived JWT carrying the OAuth identity. Issued only when
   *  ``requires_onboarding`` is true. */
  onboarding_token: string | null;
  /** Server-suggested placeholder for the workspace-name prompt.
   *  Mirrors the old auto-naming template; the user can override. */
  suggested_workspace_name: string | null;
}

export interface SelectWorkspacePayload {
  selection_token: string;
  workspace_id: string;
}

export interface CompleteOAuthOnboardingPayload {
  onboarding_token: string;
  workspace_name: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    /** Human-readable failure message. ALWAYS a string — even on
     *  422 responses whose body is a Pydantic ``{detail: [{loc, msg,
     *  type, input, ctx}, ...]}`` array. ``normalizeErrorDetail``
     *  flattens that shape before construction so call sites can
     *  freely ``setError(err.detail)`` into React state without
     *  blowing up the render with "Objects are not valid as a React
     *  child". */
    public detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

/** Flatten any error body shape produced by FastAPI into a single
 *  human-readable string. Three shapes survive in the wild:
 *  - ``{detail: "string"}`` — handlers using ``HTTPException(detail=...)``.
 *  - ``{detail: [{loc, msg, type, input, ctx}, ...]}`` — Pydantic
 *    request-validation failures (422). The array can carry more
 *    than one issue when multiple fields fail at once.
 *  - ``{detail: {msg: ...}}`` — uncommon, but seen on custom 4xx
 *    payloads. We extract ``msg`` for symmetry.
 *  Anything else falls back to ``HTTP <status>`` so React always gets
 *  a string to render. */
export function normalizeErrorDetail(body: unknown, status: number): string {
  if (typeof body === 'string') return body || `HTTP ${status}`;
  if (body && typeof body === 'object') {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.length > 0) return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => formatValidationItem(item))
        .filter((p): p is string => Boolean(p));
      if (parts.length > 0) return parts.join('; ');
    }
    if (detail && typeof detail === 'object') {
      const msg = (detail as { msg?: unknown }).msg;
      if (typeof msg === 'string' && msg.length > 0) return msg;
    }
  }
  return `HTTP ${status}`;
}

function formatValidationItem(item: unknown): string | null {
  if (typeof item === 'string') return item;
  if (!item || typeof item !== 'object') return null;
  const obj = item as { msg?: unknown; loc?: unknown };
  const msg = typeof obj.msg === 'string' ? obj.msg : null;
  if (!msg) return null;
  // ``loc`` is conventionally ["body", "email"] / ["query", "limit"] /
  // ["body", "items", 0, "name"]. Use the last non-source-tag segment
  // as the field name so the user sees "email: ..." instead of just
  // "value is not a valid email address".
  const loc = Array.isArray(obj.loc) ? obj.loc : null;
  const field =
    loc && loc.length > 1
      ? loc
          .slice(1)
          .filter((p) => typeof p === 'string' || typeof p === 'number')
          .join('.')
      : null;
  return field ? `${field}: ${msg}` : msg;
}

// Global 401 handler. AuthProvider registers this on mount; api code
// invokes it whenever the backend returns 401 on an authenticated
// request (token expired / revoked / workspace removed). Auth-bearing
// endpoints (/auth/login, /auth/select-workspace, /auth/register) are
// excluded — there a 401 just means "wrong credentials" and shouldn't
// trigger a redirect loop.
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  onUnauthorized = fn;
}

const AUTH_PATHS_NO_REDIRECT = new Set([
  `${V1}/auth/login`,
  `${V1}/auth/register`,
  `${V1}/auth/select-workspace`,
]);

function authHeader(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function maybeUnauthorized(path: string, status: number): void {
  if (status !== 401) return;
  if (AUTH_PATHS_NO_REDIRECT.has(path)) return;
  onUnauthorized?.();
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader(),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = normalizeErrorDetail(body, response.status);
    maybeUnauthorized(path, response.status);
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

// Helper for the bare-fetch sites (DELETE / 201-no-body endpoints) so
// they share the same 401 handling as request<T>().
async function requestVoid(path: string, init: RequestInit = {}): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...authHeader(),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = normalizeErrorDetail(body, response.status);
    maybeUnauthorized(path, response.status);
    throw new ApiError(response.status, detail);
  }
}

export const authApi = {
  login: (payload: LoginPayload) =>
    request<LoginResponse>(`${V1}/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  register: (payload: RegisterPayload) =>
    request<TokenResponse>(`${V1}/auth/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  selectWorkspace: (payload: SelectWorkspacePayload) =>
    request<TokenResponse>(`${V1}/auth/select-workspace`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  completeOnboarding: (payload: CompleteOAuthOnboardingPayload) =>
    request<TokenResponse>(`${V1}/auth/complete-oauth-onboarding`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// ---------- Me (self profile) ----------

export interface MeProfile {
  user_id: string;
  email: string;
  full_name: string;
  has_password: boolean;
  oauth_provider: 'GOOGLE' | 'GITHUB' | null;
  member_id: string;
  workspace_id: string;
  workspace_name: string;
  role: 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';
  type: 'HUMAN' | 'AGENT';
  team_id: string | null;
  team_role: TeamRole | null;
}

export interface MeStats {
  assigned_count: number;
  completed_count: number;
  avg_resolution_seconds: number | null;
  last_activity_at: string | null;
  total_tokens_used: number;
}

export interface UpdateMePayload {
  full_name: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export const meApi = {
  get: () => request<MeProfile>(`${V1}/me`),
  update: (payload: UpdateMePayload) =>
    request<MeProfile>(`${V1}/me`, { method: 'PATCH', body: JSON.stringify(payload) }),
  changePassword: (payload: ChangePasswordPayload) =>
    requestVoid(`${V1}/me/password`, { method: 'POST', body: JSON.stringify(payload) }),
  stats: () => request<MeStats>(`${V1}/me/stats`),
  // Phase 4 — notifications inbox
  notifications: () => request<NotificationItem[]>(`${V1}/me/notifications`),
  unreadCount: () => request<NotificationCount>(`${V1}/me/notifications/unread-count`),
  markRead: (id: string) =>
    requestVoid(`${V1}/me/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' }),
  markAllRead: () => requestVoid(`${V1}/me/notifications/read-all`, { method: 'POST' }),
  // Phase 5 batch 1 — workspace switcher
  workspaces: () => request<MeWorkspace[]>(`${V1}/me/workspaces`),
  createWorkspace: (payload: CreateMyWorkspacePayload) =>
    request<CreateMyWorkspaceResponse>(`${V1}/me/workspaces`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  // Phase 5 batch 3 — role-scoped dashboard
  dashboard: () => request<DashboardResponse>(`${V1}/me/dashboard`),
};

export interface DashboardScope {
  label: string;
  is_admin: boolean;
  member_id: string | null;
  team_id: string | null;
  project_count: number;
}

export interface DashboardResponse {
  scope: DashboardScope;
  tasks: Task[];
}

export const authSwitchApi = {
  switchWorkspace: (payload: { workspace_id: string }) =>
    request<TokenResponse>(`${V1}/auth/switch-workspace`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export interface MeWorkspace {
  workspace_id: string;
  name: string;
  role: 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';
  member_id: string;
  is_current: boolean;
}

export interface CreateMyWorkspacePayload {
  name: string;
}

export interface CreateMyWorkspaceResponse {
  workspace_id: string;
  name: string;
  member_id: string;
  access_token: string;
  expires_in: number;
}

export type NotificationKind = 'MENTION_TASK' | 'MENTION_COMMENT';

export interface NotificationItem {
  id: string;
  type: NotificationKind;
  source_task_id: string | null;
  source_comment_id: string | null;
  source_member_id: string | null;
  source_member_name: string | null;
  preview: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationCount {
  unread: number;
}

// ---------- Tenants ----------

// Org-level role. Renamed in Phase 1 to disambiguate from TeamRole
// (which uses MEMBER too) and to read clearly in JWTs / audit log.
export type MemberRole = 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';
export type MemberKind = 'HUMAN' | 'AGENT';
// HEAD was removed in migration 0022 — Department Head is now an
// attribute of a Department (``Department.head_id``), not a per-team
// rank. The remaining TeamRole values are pure intra-team ranks.
export type TeamRole = 'MANAGER' | 'LEAD' | 'MEMBER';

/** Compact summary of the Department a member's Team belongs to.
 *  Returned by the api on PATCH /tenants/members/{id}/team (resolved
 *  from team.department_id) so the UI can render User -> Team ->
 *  Department without a follow-up call. Optional + nullable because
 *  list / GET endpoints don't necessarily populate it; consumers
 *  fall back to the (teams + departments) client cache when absent. */
export interface MemberDepartmentSummary {
  id: string;
  name: string;
}

export interface Member {
  id: string;
  workspace_id: string;
  name: string;
  email: string | null;
  type: MemberKind;
  role: MemberRole;
  priority: number;
  // Section 1: intra-team rank, set when the member is assigned to a
  // Team. Null when unassigned.
  team_id: string | null;
  team_role: TeamRole | null;
  // Workspace-scoped soft lock. When true, every workspace-scoped
  // request from this member's JWT is rejected with 403 by the api.
  // The user can still log in to OTHER workspaces where they're not
  // suspended.
  is_suspended: boolean;
  /** Resolved server-side on writes that touch team_id (notably the
   *  PATCH /team endpoint). Null when the member is unassigned or
   *  their team is un-filed. May be absent on responses that don't
   *  bother resolving it (list / GET) — consumers fall back to the
   *  teams + departments cache. */
  department?: MemberDepartmentSummary | null;
}

export interface SetMemberSuspensionPayload {
  is_suspended: boolean;
}

export interface SetMemberTeamPayload {
  team_id: string | null;
  team_role: TeamRole | null;
}

export interface InviteCreatePayload {
  email: string;
  role: 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';
}

export interface InviteCreateResponse {
  id: string;
  workspace_id: string;
  email: string;
  role: MemberRole;
  expires_at: string;
  accept_url: string;
  // Raw token — exposed once on creation, never afterward.
  token: string;
}

export interface InvitePreview {
  workspace_name: string;
  email: string;
  role: MemberRole;
  expires_at: string;
}

export interface InviteAcceptPayload {
  full_name: string;
  password: string;
}

export interface MemberListFilters {
  name?: string;
  memberId?: string;
  role?: MemberRole;
  teamId?: string;
  projectId?: string;
  humansOnly?: boolean;
}

export interface UpdateMemberProfilePayload {
  name?: string | null;
  role?: MemberRole | null;
  priority?: number | null;
}

export interface MemberStats {
  assigned_count: number;
  completed_count: number;
  avg_resolution_seconds: number | null;
  accuracy_percent: number | null;
  last_activity_at: string | null;
  total_tokens_used: number;
}

// Priority-scoped profile shape returned by /tenants/members/{id}/profile.
// When ``is_limited_view`` is true (lower-rank admin viewing a
// higher-rank member), the restricted fields below are null.
export interface MemberProfile {
  id: string;
  workspace_id: string;
  name: string;
  email: string | null;
  type: MemberKind;
  is_limited_view: boolean;
  role: MemberRole | null;
  priority: number | null;
  team_id: string | null;
  team_role: TeamRole | null;
  is_suspended: boolean | null;
}

export interface AdminSetMemberPasswordPayload {
  new_password: string;
}

export const tenantsApi = {
  listMembers: (filters: MemberListFilters & PaginationOpts = {}) => {
    const params = new URLSearchParams();
    if (filters.name) params.set('name', filters.name);
    if (filters.memberId) params.set('member_id', filters.memberId);
    if (filters.role) params.set('role', filters.role);
    if (filters.teamId) params.set('team_id', filters.teamId);
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.humansOnly) params.set('humans_only', 'true');
    if (filters.skip != null) params.set('skip', String(filters.skip));
    if (filters.limit != null) params.set('limit', String(filters.limit));
    const qs = params.toString();
    return request<Page<Member>>(`${V1}/tenants/members${qs ? `?${qs}` : ''}`);
  },
  getMember: (id: string) => request<Member>(`${V1}/tenants/members/${id}`),
  getMemberProfile: (id: string) => request<MemberProfile>(`${V1}/tenants/members/${id}/profile`),
  getMemberStats: (id: string) => request<MemberStats>(`${V1}/tenants/members/${id}/stats`),
  updateMemberProfile: (id: string, payload: UpdateMemberProfilePayload) =>
    request<Member>(`${V1}/tenants/members/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  createInvite: (payload: InviteCreatePayload) =>
    request<InviteCreateResponse>(`${V1}/tenants/invites`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  previewInvite: (token: string) =>
    request<InvitePreview>(`${V1}/tenants/invites/${encodeURIComponent(token)}`),
  acceptInvite: (token: string, payload: InviteAcceptPayload) =>
    request<TokenResponse>(`${V1}/tenants/invites/${encodeURIComponent(token)}/accept`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  setMemberTeam: (memberId: string, payload: SetMemberTeamPayload) =>
    request<Member>(`${V1}/tenants/members/${memberId}/team`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  setMemberSuspension: (memberId: string, payload: SetMemberSuspensionPayload) =>
    request<Member>(`${V1}/tenants/members/${memberId}/suspension`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  adminSetMemberPassword: (memberId: string, payload: AdminSetMemberPasswordPayload) =>
    requestVoid(`${V1}/tenants/members/${memberId}/password`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const tasksApi = {
  list: (
    opts: {
      status?: TaskStatus;
      blockedOnly?: boolean;
      projectId?: string;
      teamId?: string;
      assigneeId?: string;
      priorityMin?: number;
      priorityMax?: number;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.status) params.set('status_filter', opts.status);
    if (opts.blockedOnly) params.set('blocked_only', 'true');
    if (opts.projectId) params.set('project_id', opts.projectId);
    if (opts.teamId) params.set('team_id', opts.teamId);
    if (opts.assigneeId) params.set('assignee_id', opts.assigneeId);
    if (opts.priorityMin != null) params.set('priority_min', String(opts.priorityMin));
    if (opts.priorityMax != null) params.set('priority_max', String(opts.priorityMax));
    const qs = params.toString();
    return request<Task[]>(`${V1}/tasks${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => request<TaskDetail>(`${V1}/tasks/${id}`),
  create: (payload: CreateTaskPayload) =>
    request<Task>(`${V1}/tasks`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateStatus: (id: string, payload: UpdateStatusPayload) =>
    request<Task>(`${V1}/tasks/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  setBlocked: (id: string, payload: SetBlockedPayload) =>
    request<Task>(`${V1}/tasks/${id}/block`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  updatePriority: (id: string, priority: number) =>
    request<Task>(`${V1}/tasks/${id}/priority`, {
      method: 'PATCH',
      body: JSON.stringify({ priority }),
    }),
  updateLinks: (id: string, payload: UpdateTaskLinksPayload) =>
    request<Task>(`${V1}/tasks/${id}/links`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  rate: (id: string, payload: RateTaskPayload) =>
    request<TaskRating>(`${V1}/tasks/${id}/rate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listActivity: (id: string) => request<TaskActivity[]>(`${V1}/tasks/${id}/activity`),
  listRequests: (id: string) => request<TaskRequest[]>(`${V1}/tasks/${id}/requests`),
  createRequest: (id: string, payload: CreateRequestPayload) =>
    request<TaskRequest>(`${V1}/tasks/${id}/requests`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listComments: (id: string) => request<TaskComment[]>(`${V1}/tasks/${id}/comments`),
  postComment: (id: string, payload: CreateCommentPayload) =>
    request<TaskComment>(`${V1}/tasks/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listRelations: (id: string) => request<TaskRelations>(`${V1}/tasks/${id}/relations`),
  // 201 with no body — request<T> would JSON-parse and explode, so
  // these go through requestVoid (which still funnels 401s to the
  // global handler so an expired token logs the user out cleanly).
  createRelation: (id: string, payload: CreateRelationPayload) =>
    requestVoid(`${V1}/tasks/${id}/relations`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteRelation: (id: string, relationId: string) =>
    requestVoid(`${V1}/tasks/${id}/relations/${relationId}`, { method: 'DELETE' }),
};

// ---------- Agents ----------

export type HealthStatus = 'ONLINE' | 'IDLE' | 'STALE';

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  priority: number;
  model: string | null;
  created_at: string;
  // Most recent api contact (heartbeat or JWT exchange). Null until
  // the agent has authenticated at least once.
  last_seen_at: string | null;
  health_status: HealthStatus;
}

export interface AgentStats {
  assigned_count: number;
  completed_count: number;
  avg_resolution_seconds: number | null;
  accuracy_percent: number | null;
  last_activity_at: string | null;
  total_tokens_used: number;
}

export interface AgentDetail extends Agent {
  stats: AgentStats;
}

export interface CreateAgentPayload {
  name: string;
  priority?: number;
  model?: string | null;
}

export interface UpdateAgentPayload {
  name?: string;
  priority?: number;
  model?: string | null;
}

export interface CreateAgentResponse extends Agent {
  // Plaintext API key. Surfaced exactly once on creation; subsequent
  // GETs return the safe Agent shape only — bcrypt-hashed on persist.
  api_key: string;
}

export const agentsApi = {
  list: () => request<Agent[]>(`${V1}/agents`),
  get: (id: string) => request<AgentDetail>(`${V1}/agents/${id}`),
  create: (payload: CreateAgentPayload) =>
    request<CreateAgentResponse>(`${V1}/agents`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: UpdateAgentPayload) =>
    request<Agent>(`${V1}/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  // Returns 204 (no body). request<T> would JSON-parse — handle via
  // requestVoid so 401s still flow to the global logout handler.
  remove: (id: string) => requestVoid(`${V1}/agents/${id}`, { method: 'DELETE' }),
};

export interface RateTaskPayload {
  score: number;
  feedback?: string | null;
}

export interface TaskRating {
  task_id: string;
  rated_by_id: string;
  rated_member_id: string | null;
  score: number;
  feedback: string | null;
  created_at: string;
}

// ---------- Projects ----------

export type ProjectStatus = 'ACTIVE' | 'ARCHIVED';

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectPayload {
  name: string;
  description?: string | null;
}

export interface UpdateProjectPayload {
  name?: string;
  description?: string | null;
  status?: ProjectStatus;
}

export const projectsApi = {
  list: (opts: { includeArchived?: boolean } & PaginationOpts = {}) => {
    const params = new URLSearchParams();
    if (opts.includeArchived) params.set('include_archived', 'true');
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<Project>>(`${V1}/projects${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => request<Project>(`${V1}/projects/${id}`),
  create: (payload: CreateProjectPayload) =>
    request<Project>(`${V1}/projects`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: UpdateProjectPayload) =>
    request<Project>(`${V1}/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  remove: (id: string) => requestVoid(`${V1}/projects/${id}`, { method: 'DELETE' }),
  listTasks: (id: string) => request<Task[]>(`${V1}/projects/${id}/tasks`),
  history: (id: string) => request<ProjectHistory>(`${V1}/projects/${id}/history`),
};

export interface ProjectHistorySummary {
  total_tasks: number;
  by_status: Record<TaskStatus, number>;
  blocked_now: number;
  avg_resolution_seconds: number | null;
  total_tokens_used: number;
  rated_count: number;
  avg_rating: number | null;
}

export interface ProjectTaskHistory {
  id: string;
  public_id: string;
  title: string;
  status: TaskStatus;
  is_blocked: boolean;
  blocked_reason: string | null;
  description: string | null;
  priority: number;
  assignee_id: string | null;
  project_id: string | null;
  team_id: string | null;
  tokens_used: number;
  created_at: string;
  completed_at: string | null;
  rating: TaskRating | null;
  activities: TaskActivity[];
  comments: TaskComment[];
}

export interface ProjectHistory {
  project: Project;
  summary: ProjectHistorySummary;
  tasks: ProjectTaskHistory[];
}

// ---------- Departments ----------

export interface DepartmentHead {
  id: string;
  name: string;
  email: string | null;
  type: MemberKind;
}

export interface Department {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  /** Member id of the Department Head, or null when no head is set. */
  head_id: string | null;
  /** Denormalised head summary so the UI can render the name without a
   *  follow-up /members/{id} call. Null when ``head_id`` is null. */
  head: DepartmentHead | null;
  created_at: string;
  updated_at: string;
}

export interface CreateDepartmentPayload {
  name: string;
  description?: string | null;
  /** Optional Department Head. Must reference a member of the same
   *  workspace; the api returns 422 otherwise. */
  head_id?: string | null;
}

export interface UpdateDepartmentPayload {
  name?: string | null;
  description?: string | null;
  /** Setting to null clears the head; omitting the field leaves it
   *  unchanged. */
  head_id?: string | null;
}

export const departmentsApi = {
  list: (opts: { name?: string } & PaginationOpts = {}) => {
    const params = new URLSearchParams();
    if (opts.name) params.set('name', opts.name);
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<Department>>(`${V1}/departments${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => request<Department>(`${V1}/departments/${id}`),
  create: (payload: CreateDepartmentPayload) =>
    request<Department>(`${V1}/departments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: UpdateDepartmentPayload) =>
    request<Department>(`${V1}/departments/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  remove: (id: string) => requestVoid(`${V1}/departments/${id}`, { method: 'DELETE' }),
};

// ---------- Teams ----------

export interface TeamRecord {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  department_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateTeamPayload {
  name: string;
  description?: string | null;
  department_id?: string | null;
}

export interface UpdateTeamPayload {
  name?: string | null;
  description?: string | null;
  department_id?: string | null;
}

export const requestsApi = {
  listInbox: (teamId: string, status?: RequestStatus) => {
    const qs = status ? `?status_filter=${status}` : '';
    return request<TaskRequest[]>(`${V1}/teams/${teamId}/requests${qs}`);
  },
  fulfill: (requestId: string, payload: FulfillRequestPayload) =>
    request<TaskRequest>(`${V1}/requests/${requestId}/fulfill`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reject: (requestId: string, payload: RejectRequestPayload) =>
    request<TaskRequest>(`${V1}/requests/${requestId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const teamsApi = {
  list: (opts: { departmentId?: string } & PaginationOpts = {}) => {
    const params = new URLSearchParams();
    if (opts.departmentId) params.set('department_id', opts.departmentId);
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<TeamRecord>>(`${V1}/teams${qs ? `?${qs}` : ''}`);
  },
  create: (payload: CreateTeamPayload) =>
    request<TeamRecord>(`${V1}/teams`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: UpdateTeamPayload) =>
    request<TeamRecord>(`${V1}/teams/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  remove: (id: string) => requestVoid(`${V1}/teams/${id}`, { method: 'DELETE' }),
};

// ---------- Audit logs ----------

export type AuditAction =
  | 'CREATED'
  | 'UPDATED'
  | 'DELETED'
  | 'SUSPENDED'
  | 'SUSPENSION_REVOKED'
  | 'ROLE_CHANGED'
  | 'TEAM_ASSIGNED'
  | 'TEAM_UNASSIGNED';

export type AuditResourceType = 'WORKSPACE' | 'DEPARTMENT' | 'TEAM' | 'MEMBER';

export interface AuditLog {
  id: string;
  workspace_id: string;
  actor_member_id: string | null;
  actor_name: string | null;
  action: AuditAction;
  resource_type: AuditResourceType;
  resource_id: string | null;
  // Free-form per AuditAction. Common shapes:
  // - CREATED: {<field>: <value>, ...}
  // - UPDATED: {<field>: {from, to}, ...}
  // - DELETED: {<field>: <captured_value>, ...}
  // - SUSPENDED / SUSPENSION_REVOKED: {member_name, member_email}
  // - ROLE_CHANGED: {from, to, member_name}
  // - TEAM_ASSIGNED / TEAM_UNASSIGNED: {to_team_id?, from_team_id?,
  //                                     to_team_role?, from_team_role?,
  //                                     member_name}
  changes: Record<string, unknown>;
  created_at: string;
}

export const auditApi = {
  list: (opts: PaginationOpts = {}) => {
    const params = new URLSearchParams();
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<AuditLog>>(`${V1}/audit/logs${qs ? `?${qs}` : ''}`);
  },
};

// ---------- Workspaces ----------

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  task_prefix: string;
  created_at: string;
  updated_at: string;
}

export interface RenameWorkspacePayload {
  name: string;
}

export const workspacesApi = {
  rename: (id: string, payload: RenameWorkspacePayload) =>
    request<Workspace>(`${V1}/workspaces/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
};

// Paginated Blocks page. Distinct from ``tasksApi.list({blockedOnly})``
// which still returns the unpaginated array used by the AppShell
// sidebar badge and the Dashboard panel.
export type BlocksSort = 'priority' | 'newest' | 'oldest';

export interface BlocksListOpts extends PaginationOpts {
  status?: TaskStatus;
  teamId?: string;
  projectId?: string;
  assigneeId?: string;
  sort?: BlocksSort;
}

export const blocksApi = {
  list: (opts: BlocksListOpts = {}) => {
    const params = new URLSearchParams();
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    if (opts.status) params.set('status', opts.status);
    if (opts.teamId) params.set('team_id', opts.teamId);
    if (opts.projectId) params.set('project_id', opts.projectId);
    if (opts.assigneeId) params.set('assignee_id', opts.assigneeId);
    if (opts.sort) params.set('sort', opts.sort);
    const qs = params.toString();
    return request<Page<Task>>(`${V1}/blocks${qs ? `?${qs}` : ''}`);
  },
};
