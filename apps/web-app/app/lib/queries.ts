'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import {
  agentsApi,
  tasksApi,
  tenantsApi,
  type Agent,
  type AgentDetail,
  type CreateAgentPayload,
  type CreateAgentResponse,
  type CreateCommentPayload,
  type CreateRelationPayload,
  type CreateTaskPayload,
  type InviteCreatePayload,
  type InviteCreateResponse,
  type Member,
  type RateTaskPayload,
  type SetBlockedPayload,
  type Task,
  type TaskComment,
  type TaskDetail,
  type TaskRating,
  type TaskRelations,
  type TaskStatus,
  type UpdateAgentPayload,
  type UpdateStatusPayload,
} from './api';

export const taskKeys = {
  all: ['tasks'] as const satisfies QueryKey,
  list: (opts: { status?: TaskStatus; blockedOnly?: boolean } = {}) => {
    if (opts.blockedOnly) return ['tasks', { blockedOnly: true }] as const satisfies QueryKey;
    if (opts.status) return ['tasks', { status: opts.status }] as const satisfies QueryKey;
    return ['tasks'] as const satisfies QueryKey;
  },
  detail: (id: string) => ['tasks', id] as const satisfies QueryKey,
  comments: (id: string) => ['tasks', id, 'comments'] as const satisfies QueryKey,
  relations: (id: string) => ['tasks', id, 'relations'] as const satisfies QueryKey,
};

export function useTasks() {
  return useQuery({
    queryKey: taskKeys.list(),
    queryFn: () => tasksApi.list(),
  });
}

export function useBlockedTasks() {
  return useQuery({
    queryKey: taskKeys.list({ blockedOnly: true }),
    queryFn: () => tasksApi.list({ blockedOnly: true }),
    // The Exception Queue should feel responsive — keep it fresh.
    refetchInterval: 15_000,
  });
}

export function useTask(id: string) {
  return useQuery<TaskDetail>({
    queryKey: taskKeys.detail(id),
    queryFn: () => tasksApi.get(id),
  });
}

export function useTaskComments(id: string) {
  return useQuery<TaskComment[]>({
    queryKey: taskKeys.comments(id),
    queryFn: () => tasksApi.listComments(id),
  });
}

export function usePostComment(id: string) {
  const qc = useQueryClient();
  return useMutation<TaskComment, Error, CreateCommentPayload>({
    mutationFn: (payload) => tasksApi.postComment(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: taskKeys.comments(id) });
    },
  });
}

export function useSetTaskBlocked(id: string) {
  const qc = useQueryClient();
  return useMutation<Task, Error, SetBlockedPayload>({
    mutationFn: (payload) => tasksApi.setBlocked(id, payload),
    onSuccess: () => {
      // Block-flag is shown on board, exception queue and detail —
      // bust them all so the new flag propagates.
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

export function useTaskRelations(id: string) {
  return useQuery<TaskRelations>({
    queryKey: taskKeys.relations(id),
    queryFn: () => tasksApi.listRelations(id),
  });
}

export function useCreateRelation(id: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, CreateRelationPayload>({
    mutationFn: (payload) => tasksApi.createRelation(id, payload),
    onSuccess: (_data, vars) => {
      // Both ends of the link change — bust this task's relations and
      // the counterpart's. Detail responses now embed relations, so
      // the detail caches also need invalidating.
      qc.invalidateQueries({ queryKey: taskKeys.relations(id) });
      qc.invalidateQueries({ queryKey: taskKeys.relations(vars.target_task_id) });
      qc.invalidateQueries({ queryKey: taskKeys.detail(id) });
      qc.invalidateQueries({ queryKey: taskKeys.detail(vars.target_task_id) });
    },
  });
}

export function useDeleteRelation(id: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, { relationId: string; counterpartTaskId: string }>({
    mutationFn: ({ relationId }) => tasksApi.deleteRelation(id, relationId),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: taskKeys.relations(id) });
      qc.invalidateQueries({ queryKey: taskKeys.relations(vars.counterpartTaskId) });
      qc.invalidateQueries({ queryKey: taskKeys.detail(id) });
      qc.invalidateQueries({ queryKey: taskKeys.detail(vars.counterpartTaskId) });
    },
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

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation<Task, Error, CreateTaskPayload>({
    mutationFn: (payload) => tasksApi.create(payload),
    // Drop the lists from cache so the new task appears in the board /
    // dashboard / blocked views without a manual refresh.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

// ---------- Agents ----------

export const agentKeys = {
  all: ['agents'] as const satisfies QueryKey,
  detail: (id: string) => ['agents', id] as const satisfies QueryKey,
};

export function useAgents() {
  return useQuery<Agent[]>({
    queryKey: agentKeys.all,
    queryFn: () => agentsApi.list(),
  });
}

export function useAgent(id: string) {
  return useQuery<AgentDetail>({
    queryKey: agentKeys.detail(id),
    queryFn: () => agentsApi.get(id),
    // Stats refresh fairly often — agents pick up tasks throughout the
    // day, so a 30s background refresh keeps the dashboard meaningful
    // without spamming the api.
    refetchInterval: 30_000,
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation<CreateAgentResponse, Error, CreateAgentPayload>({
    mutationFn: (payload) => agentsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.all });
    },
  });
}

export function useUpdateAgent(id: string) {
  const qc = useQueryClient();
  return useMutation<Agent, Error, UpdateAgentPayload>({
    mutationFn: (payload) => agentsApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.all });
      qc.invalidateQueries({ queryKey: agentKeys.detail(id) });
    },
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => agentsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentKeys.all });
    },
  });
}

export function useRateTask() {
  const qc = useQueryClient();
  return useMutation<TaskRating, Error, { id: string; payload: RateTaskPayload }>({
    mutationFn: ({ id, payload }) => tasksApi.rate(id, payload),
    onSuccess: () => {
      // Ratings drive agent stats — bust the agent caches so the
      // accuracy_percent reflects the new rating on next render.
      qc.invalidateQueries({ queryKey: agentKeys.all });
    },
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
      const previousBlocked = qc.getQueryData<Task[]>(taskKeys.list({ blockedOnly: true }));

      qc.setQueryData<Task[] | undefined>(taskKeys.list(), (prev) =>
        prev?.map((t) => (t.id === id ? { ...t, status: payload.status } : t)),
      );

      return { previousAll, previousBlocked };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previousAll) qc.setQueryData(taskKeys.list(), ctx.previousAll);
      if (ctx?.previousBlocked)
        qc.setQueryData(taskKeys.list({ blockedOnly: true }), ctx.previousBlocked);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}
