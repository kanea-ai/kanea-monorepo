// Thin fetch wrapper for the FastAPI backend.
// Auth: token is read from localStorage on the client; tests/server reads use
// the empty-string fallback and the route returns 401, which surfaces in
// React Query's error state.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

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

function authHeader(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage.getItem('kanea_token');
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
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const tasksApi = {
  list: (status?: TaskStatus) => {
    const qs = status ? `?status_filter=${status}` : '';
    return request<Task[]>(`/tasks${qs}`);
  },
  updateStatus: (id: string, payload: UpdateStatusPayload) =>
    request<Task>(`/tasks/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
};
