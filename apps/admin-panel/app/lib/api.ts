// API client for the back-office. Mirrors the web-app's surface where
// the shapes overlap (Page, error normalisation) but only exposes the
// `/api/v1/admin/*` endpoints — there is no reason for the admin app
// to call workspace-scoped routes directly.

// In prod the admin-panel is served from admin.kanea.ai and the LB url-map
// routes /api/* on that host to be-api — so an empty default means every
// fetch goes same-origin and lands at the right backend without any env
// plumbing. Local dev overrides this via .env.development
// (NEXT_PUBLIC_API_BASE_URL=http://localhost:8000). NEXT_PUBLIC_* values
// are baked into the client bundle at `next build` time, not picked up
// from Cloud Run runtime env — keeping the default empty avoids that
// trap for the prod build entirely.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';
const V1 = '/api/v1';

export const TOKEN_STORAGE_KEY = 'kanea.admin.bearer';

export interface Page<T> {
  items: T[];
  total: number;
}

export interface WorkspaceMetrics {
  total_users: number;
  total_tasks: number;
  total_tokens_used: number;
}

export interface AdminWorkspaceRow {
  id: string;
  name: string;
  slug: string;
  task_prefix: string;
  suspended_at: string | null;
  created_at: string;
  updated_at: string;
  metrics: WorkspaceMetrics;
}

export interface SuspendWorkspacePayload {
  is_suspended: boolean;
}

// ---------- users ----------

export type WorkspaceRole = 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_USER';

export interface AdminUserRow {
  id: string;
  email: string;
  full_name: string;
  is_superadmin: boolean;
  is_banned: boolean;
  sessions_invalidated_at: string | null;
  created_at: string;
  workspace_count: number;
}

export interface AdminUserMembership {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  member_id: string;
  role: WorkspaceRole;
  is_suspended: boolean;
}

export interface AdminUserDetail {
  id: string;
  email: string;
  full_name: string;
  is_superadmin: boolean;
  is_banned: boolean;
  sessions_invalidated_at: string | null;
  created_at: string;
  memberships: AdminUserMembership[];
}

export interface BanUserPayload {
  is_banned: boolean;
}

export interface ForcePasswordResetResponse {
  user_id: string;
  sessions_invalidated_at: string;
  simulated_email: string;
}

// ---------- metrics ----------

export interface RecentSignup {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface PlatformMetrics {
  total_active_workspaces: number;
  total_registered_users: number;
  total_tokens_used: number;
  recent_signups: RecentSignup[];
}

// ---------- tenant drill-down ----------

export interface WorkspaceStatusBreakdown {
  pending: number;
  in_progress: number;
  in_review: number;
  done: number;
  cancelled: number;
  blocked: number;
}

export interface AdminWorkspaceDetail {
  id: string;
  name: string;
  slug: string;
  task_prefix: string;
  suspended_at: string | null;
  created_at: string;
  updated_at: string;
  total_users: number;
  total_tasks: number;
  total_tokens_used: number;
  total_teams: number;
  total_departments: number;
  total_projects: number;
  status_breakdown: WorkspaceStatusBreakdown;
}

export type TeamRoleValue = 'MANAGER' | 'LEAD' | 'MEMBER';

export interface AdminWorkspaceUserRow {
  member_id: string;
  user_id: string;
  email: string | null;
  full_name: string;
  type: 'HUMAN' | 'AGENT';
  role: WorkspaceRole;
  is_suspended: boolean;
  team_id: string | null;
  team_name: string | null;
  team_role: TeamRoleValue | null;
  team_department_id: string | null;
  team_department_name: string | null;
  headed_department_id: string | null;
  headed_department_name: string | null;
}

export interface PatchWorkspaceUserPayload {
  team_id?: string | null;
  team_role?: TeamRoleValue | null;
  department_id?: string | null;
}

export interface LoginPayload {
  email: string;
  password: string;
}

// /auth/login returns one of two shapes depending on multi-workspace
// membership. We only need the access_token field for the back-office;
// if the user has multiple workspaces we'll exchange the select token
// for the first available workspace JWT.
export interface LoginResponse {
  // Single-workspace user → workspace-bound JWT.
  access_token?: string;
  expires_in?: number;
  // Multi-workspace user → short-lived "select" token + workspace list.
  select_token?: string;
  workspaces?: { workspace_id: string; name: string; role: string }[];
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  token_type?: string;
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

/** Flatten any FastAPI / Pydantic error body into a string. Same
 *  contract the web-app uses; copied here so the admin app can hand
 *  a clean string to React state without ever rendering a raw
 *  validation-error object. */
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
    const body = await response.json().catch(() => null);
    const detail = normalizeErrorDetail(body, response.status);
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

// /auth/login + /auth/select-workspace endpoints. The admin app reuses
// the same login flow as the web-app; the only difference is what it
// does with the bearer afterward (drive /admin/* requests).
export const authApi = {
  login: (payload: LoginPayload) =>
    request<LoginResponse>(`${V1}/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  selectWorkspace: (payload: { workspace_id: string }) =>
    request<TokenResponse>(`${V1}/auth/select-workspace`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export const adminApi = {
  health: () => request<{ status: string; email: string }>(`${V1}/admin/health`),
  listWorkspaces: (opts: { name?: string; sort?: string; skip?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.name) params.set('name', opts.name);
    if (opts.sort) params.set('sort', opts.sort);
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<AdminWorkspaceRow>>(`${V1}/admin/workspaces${qs ? `?${qs}` : ''}`);
  },
  setWorkspaceSuspended: (workspaceId: string, payload: SuspendWorkspacePayload) =>
    request<AdminWorkspaceRow>(`${V1}/admin/workspaces/${workspaceId}/suspend`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  listUsers: (opts: { name?: string; skip?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.name) params.set('name', opts.name);
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<AdminUserRow>>(`${V1}/admin/users${qs ? `?${qs}` : ''}`);
  },
  getUser: (userId: string) => request<AdminUserDetail>(`${V1}/admin/users/${userId}`),
  setUserBanned: (userId: string, payload: BanUserPayload) =>
    request<AdminUserDetail>(`${V1}/admin/users/${userId}/ban`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  forceUserPasswordReset: (userId: string) =>
    request<ForcePasswordResetResponse>(`${V1}/admin/users/${userId}/force-password-reset`, {
      method: 'POST',
    }),
  metrics: () => request<PlatformMetrics>(`${V1}/admin/metrics`),
  getWorkspaceDetail: (workspaceId: string) =>
    request<AdminWorkspaceDetail>(`${V1}/admin/workspaces/${workspaceId}`),
  listWorkspaceUsers: (
    workspaceId: string,
    opts: { name?: string; skip?: number; limit?: number } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.name) params.set('name', opts.name);
    if (opts.skip != null) params.set('skip', String(opts.skip));
    if (opts.limit != null) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return request<Page<AdminWorkspaceUserRow>>(
      `${V1}/admin/workspaces/${workspaceId}/users${qs ? `?${qs}` : ''}`,
    );
  },
  patchWorkspaceUser: (workspaceId: string, userId: string, payload: PatchWorkspaceUserPayload) =>
    request<AdminWorkspaceUserRow>(`${V1}/admin/workspaces/${workspaceId}/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
};
