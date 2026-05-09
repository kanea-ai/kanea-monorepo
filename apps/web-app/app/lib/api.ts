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

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'CANCELLED';

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

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

function authHeader(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
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
    const detail = await response
      .json()
      .then((b: { detail?: string }) => b.detail)
      .catch(() => response.statusText);
    throw new ApiError(response.status, detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const authApi = {
  login: (payload: LoginPayload) =>
    request<TokenResponse>(`${V1}/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  register: (payload: RegisterPayload) =>
    request<TokenResponse>(`${V1}/auth/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// ---------- Tenants ----------

export type MemberRole = 'OWNER' | 'ADMIN' | 'MEMBER';
export type MemberKind = 'HUMAN' | 'AGENT';

export interface Member {
  id: string;
  workspace_id: string;
  name: string;
  email: string | null;
  type: MemberKind;
  role: MemberRole;
  priority: number;
}

export interface InviteCreatePayload {
  email: string;
  role: 'ADMIN' | 'MEMBER';
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

export const tenantsApi = {
  listMembers: () => request<Member[]>(`${V1}/tenants/members`),
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
};

export const tasksApi = {
  list: (
    opts: { status?: TaskStatus; blockedOnly?: boolean; projectId?: string; teamId?: string } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.status) params.set('status_filter', opts.status);
    if (opts.blockedOnly) params.set('blocked_only', 'true');
    if (opts.projectId) params.set('project_id', opts.projectId);
    if (opts.teamId) params.set('team_id', opts.teamId);
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
  listComments: (id: string) => request<TaskComment[]>(`${V1}/tasks/${id}/comments`),
  postComment: (id: string, payload: CreateCommentPayload) =>
    request<TaskComment>(`${V1}/tasks/${id}/comments`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listRelations: (id: string) => request<TaskRelations>(`${V1}/tasks/${id}/relations`),
  createRelation: async (id: string, payload: CreateRelationPayload): Promise<void> => {
    // 201 with no body — request<T> would JSON-parse and explode.
    const response = await fetch(`${API_BASE}${V1}/tasks/${id}/relations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await response
        .json()
        .then((b: { detail?: string }) => b.detail)
        .catch(() => response.statusText);
      throw new ApiError(response.status, detail || `HTTP ${response.status}`);
    }
  },
  deleteRelation: async (id: string, relationId: string): Promise<void> => {
    const response = await fetch(`${API_BASE}${V1}/tasks/${id}/relations/${relationId}`, {
      method: 'DELETE',
      headers: { ...authHeader() },
    });
    if (!response.ok) {
      const detail = await response
        .json()
        .then((b: { detail?: string }) => b.detail)
        .catch(() => response.statusText);
      throw new ApiError(response.status, detail || `HTTP ${response.status}`);
    }
  },
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
  // Returns 204 (no body). request<T> would JSON-parse — handle inline.
  remove: async (id: string): Promise<void> => {
    const response = await fetch(`${API_BASE}${V1}/agents/${id}`, {
      method: 'DELETE',
      headers: { ...authHeader() },
    });
    if (!response.ok) {
      const detail = await response
        .json()
        .then((b: { detail?: string }) => b.detail)
        .catch(() => response.statusText);
      throw new ApiError(response.status, detail || `HTTP ${response.status}`);
    }
  },
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
  list: (includeArchived = false) =>
    request<Project[]>(`${V1}/projects${includeArchived ? '?include_archived=true' : ''}`),
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
  remove: async (id: string): Promise<void> => {
    const response = await fetch(`${API_BASE}${V1}/projects/${id}`, {
      method: 'DELETE',
      headers: { ...authHeader() },
    });
    if (!response.ok) {
      const detail = await response
        .json()
        .then((b: { detail?: string }) => b.detail)
        .catch(() => response.statusText);
      throw new ApiError(response.status, detail || `HTTP ${response.status}`);
    }
  },
  listTasks: (id: string) => request<Task[]>(`${V1}/projects/${id}/tasks`),
};

// ---------- Teams ----------

export interface TeamRecord {
  id: string;
  workspace_id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTeamPayload {
  name: string;
}

export const teamsApi = {
  list: () => request<TeamRecord[]>(`${V1}/teams`),
  create: (payload: CreateTeamPayload) =>
    request<TeamRecord>(`${V1}/teams`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (id: string, payload: CreateTeamPayload) =>
    request<TeamRecord>(`${V1}/teams/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  remove: async (id: string): Promise<void> => {
    const response = await fetch(`${API_BASE}${V1}/teams/${id}`, {
      method: 'DELETE',
      headers: { ...authHeader() },
    });
    if (!response.ok) {
      const detail = await response
        .json()
        .then((b: { detail?: string }) => b.detail)
        .catch(() => response.statusText);
      throw new ApiError(response.status, detail || `HTTP ${response.status}`);
    }
  },
};
