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

export type TaskStatus = 'PENDING' | 'IN_PROGRESS' | 'BLOCKED' | 'DONE' | 'CANCELLED';

export interface Task {
  id: string;
  workspace_id: string;
  created_by_id: string;
  title: string;
  status: TaskStatus;
  priority: number;
  description: string | null;
  assignee_id: string | null;
  due_at: string | null;
  blocked_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateStatusPayload {
  status: TaskStatus;
  blocked_reason?: string | null;
}

export interface CreateTaskPayload {
  title: string;
  description?: string | null;
  priority?: number;
  assignee_id?: string | null;
  due_at?: string | null;
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
  list: (status?: TaskStatus) => {
    const qs = status ? `?status_filter=${status}` : '';
    return request<Task[]>(`${V1}/tasks${qs}`);
  },
  get: (id: string) => request<Task>(`${V1}/tasks/${id}`),
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
  rate: (id: string, payload: RateTaskPayload) =>
    request<TaskRating>(`${V1}/tasks/${id}/rate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// ---------- Agents ----------

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  priority: number;
  model: string | null;
  created_at: string;
}

export interface AgentStats {
  assigned_count: number;
  completed_count: number;
  avg_resolution_seconds: number | null;
  accuracy_percent: number | null;
  last_activity_at: string | null;
  total_tokens_used: number;
}

export type HealthStatus = 'ONLINE' | 'IDLE' | 'STALE';

export interface AgentDetail extends Agent {
  // ISO timestamp of the agent's last contact (heartbeat or token
  // exchange). Null until the agent has authenticated at least once.
  last_seen_at: string | null;
  health_status: HealthStatus;
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
