'use client';

import { type QueryKey, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  adminApi,
  type AdminUserDetail,
  type AdminUserRow,
  type AdminWorkspaceRow,
  type BanUserPayload,
  type ForcePasswordResetResponse,
  type Page,
  type SuspendWorkspacePayload,
} from './api';

export const adminKeys = {
  health: ['admin', 'health'] as const satisfies QueryKey,
  workspaces: (opts: { name?: string; sort?: string; skip?: number; limit?: number }) =>
    ['admin', 'workspaces', opts] as const satisfies QueryKey,
  workspacesAll: ['admin', 'workspaces'] as const satisfies QueryKey,
  users: (opts: { name?: string; skip?: number; limit?: number }) =>
    ['admin', 'users', opts] as const satisfies QueryKey,
  usersAll: ['admin', 'users'] as const satisfies QueryKey,
  user: (id: string) => ['admin', 'user', id] as const satisfies QueryKey,
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
