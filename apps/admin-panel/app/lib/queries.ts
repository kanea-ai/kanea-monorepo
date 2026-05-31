'use client';

import { type QueryKey, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  adminApi,
  type AdminAgentRow,
  type AdminMemberStats,
  type AdminUserDetail,
  type AdminUserRow,
  type AdminWorkspaceDetail,
  type AdminWorkspaceRow,
  type AdminWorkspaceUserRow,
  type BanUserPayload,
  type ForcePasswordResetResponse,
  type Page,
  type PatchWorkspaceMemberPayload,
  type PlatformMetrics,
  type SuspendWorkspacePayload,
} from './api';

export const adminKeys = {
  health: ['admin', 'health'] as const satisfies QueryKey,
  workspaces: (opts: { name?: string; sort?: string; skip?: number; limit?: number }) =>
    ['admin', 'workspaces', opts] as const satisfies QueryKey,
  workspacesAll: ['admin', 'workspaces'] as const satisfies QueryKey,
  workspaceDetail: (id: string) => ['admin', 'workspace', id] as const satisfies QueryKey,
  workspaceUsers: (id: string, opts: { name?: string; skip?: number; limit?: number }) =>
    ['admin', 'workspace', id, 'users', opts] as const satisfies QueryKey,
  workspaceUsersAll: (id: string) =>
    ['admin', 'workspace', id, 'users'] as const satisfies QueryKey,
  memberStats: (workspaceId: string, memberId: string) =>
    ['admin', 'workspace', workspaceId, 'member', memberId, 'stats'] as const satisfies QueryKey,
  workspaceMember: (workspaceId: string, memberId: string) =>
    ['admin', 'workspace', workspaceId, 'member', memberId] as const satisfies QueryKey,
  agents: (opts: { name?: string; skip?: number; limit?: number }) =>
    ['admin', 'agents', opts] as const satisfies QueryKey,
  agentsAll: ['admin', 'agents'] as const satisfies QueryKey,
  users: (opts: { name?: string; skip?: number; limit?: number }) =>
    ['admin', 'users', opts] as const satisfies QueryKey,
  usersAll: ['admin', 'users'] as const satisfies QueryKey,
  user: (id: string) => ['admin', 'user', id] as const satisfies QueryKey,
  metrics: ['admin', 'metrics'] as const satisfies QueryKey,
};

export function useAdminHealth() {
  return useQuery({
    queryKey: adminKeys.health,
    queryFn: () => adminApi.health(),
    // Auto-refresh after a logout/login so the gate-status pill is
    // current. Cheap (no DB writes) and fires only when this query is
    // mounted (the sidebar).
    refetchOnMount: 'always',
  });
}

export function useAdminWorkspaces(opts: {
  name?: string;
  sort?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery<Page<AdminWorkspaceRow>>({
    queryKey: adminKeys.workspaces(opts),
    queryFn: () => adminApi.listWorkspaces(opts),
  });
}

export function useSetWorkspaceSuspended() {
  const qc = useQueryClient();
  return useMutation<
    AdminWorkspaceRow,
    Error,
    { workspaceId: string; payload: SuspendWorkspacePayload }
  >({
    mutationFn: ({ workspaceId, payload }) => adminApi.setWorkspaceSuspended(workspaceId, payload),
    onSuccess: () => {
      // Any cached page of workspaces is now stale — bust the family.
      qc.invalidateQueries({ queryKey: adminKeys.workspacesAll });
    },
  });
}

// ---------- users ----------

export function useAdminUsers(opts: { name?: string; skip?: number; limit?: number }) {
  return useQuery<Page<AdminUserRow>>({
    queryKey: adminKeys.users(opts),
    queryFn: () => adminApi.listUsers(opts),
  });
}

export function useAdminUser(userId: string | null) {
  return useQuery<AdminUserDetail>({
    queryKey: adminKeys.user(userId ?? ''),
    queryFn: () => adminApi.getUser(userId as string),
    enabled: !!userId,
  });
}

export function useSetUserBanned() {
  const qc = useQueryClient();
  return useMutation<AdminUserDetail, Error, { userId: string; payload: BanUserPayload }>({
    mutationFn: ({ userId, payload }) => adminApi.setUserBanned(userId, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: adminKeys.usersAll });
      qc.invalidateQueries({ queryKey: adminKeys.user(data.id) });
    },
  });
}

export function useWorkspaceDetail(workspaceId: string | null) {
  return useQuery<AdminWorkspaceDetail>({
    queryKey: adminKeys.workspaceDetail(workspaceId ?? ''),
    queryFn: () => adminApi.getWorkspaceDetail(workspaceId as string),
    enabled: !!workspaceId,
  });
}

export function useWorkspaceUsers(
  workspaceId: string | null,
  opts: { name?: string; skip?: number; limit?: number },
) {
  return useQuery<Page<AdminWorkspaceUserRow>>({
    queryKey: adminKeys.workspaceUsers(workspaceId ?? '', opts),
    queryFn: () => adminApi.listWorkspaceUsers(workspaceId as string, opts),
    enabled: !!workspaceId,
  });
}

// Member-id-keyed PATCH — the only path that can reach AGENT members
// (agents have no user row, so the user-id sibling structurally excludes
// them). Also accepts workspace_role + priority on top of the team/dept
// fields, matching the superadmin's full intervention surface.
export function usePatchWorkspaceMember(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation<
    AdminWorkspaceUserRow,
    Error,
    { memberId: string; payload: PatchWorkspaceMemberPayload }
  >({
    mutationFn: ({ memberId, payload }) =>
      adminApi.patchWorkspaceMember(workspaceId, memberId, payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: adminKeys.workspaceDetail(workspaceId) });
      qc.invalidateQueries({ queryKey: adminKeys.workspaceUsersAll(workspaceId) });
      qc.invalidateQueries({
        queryKey: adminKeys.memberStats(workspaceId, vars.memberId),
      });
    },
  });
}

export function useMemberStats(workspaceId: string | null, memberId: string | null) {
  return useQuery<AdminMemberStats>({
    queryKey: adminKeys.memberStats(workspaceId ?? '', memberId ?? ''),
    queryFn: () => adminApi.getMemberStats(workspaceId as string, memberId as string),
    enabled: !!workspaceId && !!memberId,
  });
}

export function useWorkspaceMember(workspaceId: string | null, memberId: string | null) {
  return useQuery<AdminWorkspaceUserRow>({
    queryKey: adminKeys.workspaceMember(workspaceId ?? '', memberId ?? ''),
    queryFn: () => adminApi.getWorkspaceMember(workspaceId as string, memberId as string),
    enabled: !!workspaceId && !!memberId,
  });
}

export function useAdminAgents(opts: { name?: string; skip?: number; limit?: number }) {
  return useQuery<Page<AdminAgentRow>>({
    queryKey: adminKeys.agents(opts),
    queryFn: () => adminApi.listAgents(opts),
  });
}

export function useAdminMetrics() {
  return useQuery<PlatformMetrics>({
    queryKey: adminKeys.metrics,
    queryFn: () => adminApi.metrics(),
    // Dashboard surfaces "now-ish" numbers; refresh on focus so the
    // page reads correct after a switch back from another tab.
    refetchOnWindowFocus: true,
    // Auto-refresh every 60s while the page is in the foreground —
    // long enough not to hammer the api, short enough to feel live.
    refetchInterval: 60_000,
  });
}

export function useForcePasswordReset() {
  const qc = useQueryClient();
  return useMutation<ForcePasswordResetResponse, Error, { userId: string }>({
    mutationFn: ({ userId }) => adminApi.forceUserPasswordReset(userId),
    onSuccess: (_data, vars) => {
      // The sessions_invalidated_at stamp changed; refresh the detail.
      qc.invalidateQueries({ queryKey: adminKeys.user(vars.userId) });
    },
  });
}
