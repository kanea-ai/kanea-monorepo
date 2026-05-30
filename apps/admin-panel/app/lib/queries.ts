'use client';

import { type QueryKey, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { adminApi, type AdminWorkspaceRow, type Page, type SuspendWorkspacePayload } from './api';

export const adminKeys = {
  health: ['admin', 'health'] as const satisfies QueryKey,
  workspaces: (opts: { name?: string; sort?: string; skip?: number; limit?: number }) =>
    ['admin', 'workspaces', opts] as const satisfies QueryKey,
  workspacesAll: ['admin', 'workspaces'] as const satisfies QueryKey,
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
