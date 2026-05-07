'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import {
  tasksApi,
  tenantsApi,
  type InviteCreatePayload,
  type InviteCreateResponse,
  type Member,
  type Task,
  type TaskStatus,
  type UpdateStatusPayload,
} from './api';

export const taskKeys = {
  all: ['tasks'] as const satisfies QueryKey,
  list: (status?: TaskStatus) =>
    (status ? (['tasks', { status }] as const) : (['tasks'] as const)) satisfies QueryKey,
};

export function useTasks() {
  return useQuery({
    queryKey: taskKeys.list(),
    queryFn: () => tasksApi.list(),
  });
}

export function useBlockedTasks() {
  return useQuery({
    queryKey: taskKeys.list('BLOCKED'),
    queryFn: () => tasksApi.list('BLOCKED'),
    // The Exception Queue should feel responsive — keep it fresh.
    refetchInterval: 15_000,
  });
}

// ---------- Tenants ----------

export const tenantKeys = {
  members: ['tenants', 'members'] as const satisfies QueryKey,
};

export function useMembers() {
  return useQuery<Member[]>({
    queryKey: tenantKeys.members,
    queryFn: () => tenantsApi.listMembers(),
  });
}

export function useCreateInvite() {
  // No cache invalidation needed — invites don't show in any list yet.
  // The created invite is shown inline in the response (with the token).
  return useMutation<InviteCreateResponse, Error, InviteCreatePayload>({
    mutationFn: (payload) => tenantsApi.createInvite(payload),
  });
}

export function useUpdateTaskStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateStatusPayload }) =>
      tasksApi.updateStatus(id, payload),
    // Optimistic update so dnd drops feel instant. Rolls back on error.
    onMutate: async ({ id, payload }) => {
      await qc.cancelQueries({ queryKey: taskKeys.all });
      const previousAll = qc.getQueryData<Task[]>(taskKeys.list());
      const previousBlocked = qc.getQueryData<Task[]>(taskKeys.list('BLOCKED'));

      qc.setQueryData<Task[] | undefined>(taskKeys.list(), (prev) =>
        prev?.map((t) =>
          t.id === id
            ? {
                ...t,
                status: payload.status,
                blocked_reason:
                  payload.status === 'BLOCKED' ? (payload.blocked_reason ?? null) : null,
              }
            : t,
        ),
      );

      return { previousAll, previousBlocked };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previousAll) qc.setQueryData(taskKeys.list(), ctx.previousAll);
      if (ctx?.previousBlocked) qc.setQueryData(taskKeys.list('BLOCKED'), ctx.previousBlocked);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}
