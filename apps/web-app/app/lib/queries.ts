'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import {
  agentsApi,
  auditApi,
  authSwitchApi,
  departmentsApi,
  meApi,
  projectsApi,
  requestsApi,
  tasksApi,
  teamsApi,
  tenantsApi,
  type AdminSetMemberPasswordPayload,
  type Agent,
  type AgentDetail,
  type AuditLog,
  type CreateAgentPayload,
  type CreateAgentResponse,
  type CreateCommentPayload,
  type CreateDepartmentPayload,
  type CreateProjectPayload,
  type CreateRelationPayload,
  type ChangePasswordPayload,
  type CreateMyWorkspacePayload,
  type CreateMyWorkspaceResponse,
  type CreateRequestPayload,
  type CreateTaskPayload,
  type CreateTeamPayload,
  type Department,
  type FulfillRequestPayload,
  type RejectRequestPayload,
  type RequestStatus,
  type TaskRequest,
  type InviteCreatePayload,
  type InviteCreateResponse,
  type MemberListFilters,
  type MemberStats,
  type MeProfile,
  type MeStats,
  type DashboardResponse,
  type Member,
  type MemberProfile,
  type MeWorkspace,
  type NotificationCount,
  type NotificationItem,
  type Project,
  type TokenResponse,
  type ProjectHistory,
  type RateTaskPayload,
  type SetBlockedPayload,
  type SetMemberSuspensionPayload,
  type SetMemberTeamPayload,
  type Task,
  type TaskActivity,
  type TaskComment,
  type TaskDetail,
  type TaskRating,
  type TaskRelations,
  type TaskStatus,
  type TeamRecord,
  type UpdateAgentPayload,
  type UpdateDepartmentPayload,
  type UpdateMePayload,
  type UpdateMemberProfilePayload,
  type UpdateProjectPayload,
  type UpdateStatusPayload,
  type UpdateTaskLinksPayload,
  type UpdateTeamPayload,
} from './api';

// Filters the kanban + dashboard pass to /tasks. The query cache key
// includes them so flipping a filter triggers a fresh fetch.
export interface TaskListFilters {
  status?: TaskStatus;
  blockedOnly?: boolean;
  projectId?: string;
  teamId?: string;
  assigneeId?: string;
  priorityMin?: number;
  priorityMax?: number;
}

export const taskKeys = {
  all: ['tasks'] as const satisfies QueryKey,
  list: (filters: TaskListFilters = {}) => {
    if (Object.values(filters).every((v) => v == null || v === false)) {
      return ['tasks'] as const satisfies QueryKey;
    }
    return ['tasks', filters] as const satisfies QueryKey;
  },
  detail: (id: string) => ['tasks', id] as const satisfies QueryKey,
  comments: (id: string) => ['tasks', id, 'comments'] as const satisfies QueryKey,
  relations: (id: string) => ['tasks', id, 'relations'] as const satisfies QueryKey,
  activity: (id: string) => ['tasks', id, 'activity'] as const satisfies QueryKey,
};

export function useTasks(filters: TaskListFilters = {}) {
  return useQuery({
    queryKey: taskKeys.list(filters),
    queryFn: () => tasksApi.list(filters),
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
  membersList: (filters: MemberListFilters = {}) =>
    ['tenants', 'members', filters] as const satisfies QueryKey,
  member: (id: string) => ['tenants', 'members', id] as const satisfies QueryKey,
};

export function useMembers(filters: MemberListFilters = {}) {
  return useQuery<Member[]>({
    queryKey: tenantKeys.membersList(filters),
    queryFn: () => tenantsApi.listMembers(filters),
  });
}

export function useMember(id: string) {
  return useQuery<Member>({
    queryKey: tenantKeys.member(id),
    queryFn: () => tenantsApi.getMember(id),
    enabled: !!id,
  });
}

// Priority-scoped lookup. Drives the audit-log "click the actor"
// flow — a lower-rank admin sees a reduced shape (id/name/email/type
// only). Server enforces the rule; the client just renders what
// arrives.
export function useMemberProfile(id: string | null) {
  return useQuery<MemberProfile>({
    queryKey: ['tenants', 'members', id ?? '', 'profile'],
    queryFn: () => tenantsApi.getMemberProfile(id as string),
    enabled: !!id,
  });
}

export function useMemberStats(id: string | null) {
  return useQuery<MemberStats>({
    queryKey: ['tenants', 'members', id ?? '', 'stats'],
    queryFn: () => tenantsApi.getMemberStats(id as string),
    enabled: !!id,
  });
}

export function useUpdateMemberProfile() {
  const qc = useQueryClient();
  return useMutation<Member, Error, { memberId: string; payload: UpdateMemberProfilePayload }>({
    mutationFn: ({ memberId, payload }) => tenantsApi.updateMemberProfile(memberId, payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: tenantKeys.members });
      qc.invalidateQueries({ queryKey: tenantKeys.member(vars.memberId) });
    },
  });
}

// Admin / owner password reset for another workspace member. The
// scope rule (same team, same department, or workspace-wide for
// owners) is enforced server-side; the mutation surfaces the api's
// 403 message verbatim if the principal is out of scope. No cache
// invalidation needed — the password isn't on any list response.
export function useAdminSetMemberPassword() {
  return useMutation<void, Error, { memberId: string; payload: AdminSetMemberPasswordPayload }>({
    mutationFn: ({ memberId, payload }) => tenantsApi.adminSetMemberPassword(memberId, payload),
  });
}

// Workspace-scoped soft-lock toggle. After flipping, the directory and
// the member detail panel both need to refresh — the suspended pill is
// painted from the member's `is_suspended` field.
export function useSetMemberSuspension() {
  const qc = useQueryClient();
  return useMutation<Member, Error, { memberId: string; payload: SetMemberSuspensionPayload }>({
    mutationFn: ({ memberId, payload }) => tenantsApi.setMemberSuspension(memberId, payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: tenantKeys.members });
      qc.invalidateQueries({ queryKey: tenantKeys.member(vars.memberId) });
    },
  });
}

// ---------- Me ----------

export const meKeys = {
  profile: ['me'] as const satisfies QueryKey,
  stats: ['me', 'stats'] as const satisfies QueryKey,
};

export function useMe() {
  return useQuery<MeProfile>({ queryKey: meKeys.profile, queryFn: () => meApi.get() });
}

// Role-scoped dashboard data. The api decides what subset of tasks
// the current principal should see, plus a small `scope` blob the UI
// uses to label the view ("Workspace" / "Your team" / etc.).
export function useDashboard() {
  return useQuery<DashboardResponse>({
    queryKey: ['me', 'dashboard'],
    queryFn: () => meApi.dashboard(),
  });
}

export function useMeStats() {
  return useQuery<MeStats>({ queryKey: meKeys.stats, queryFn: () => meApi.stats() });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation<MeProfile, Error, UpdateMePayload>({
    mutationFn: (payload) => meApi.update(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: meKeys.profile });
      qc.invalidateQueries({ queryKey: tenantKeys.members });
    },
  });
}

export function useChangePassword() {
  return useMutation<void, Error, ChangePasswordPayload>({
    mutationFn: (payload) => meApi.changePassword(payload),
  });
}

// ---------- Notifications ----------

export const notificationKeys = {
  all: ['notifications'] as const satisfies QueryKey,
  unread: ['notifications', 'unread'] as const satisfies QueryKey,
};

export function useNotifications() {
  return useQuery<NotificationItem[]>({
    queryKey: notificationKeys.all,
    queryFn: () => meApi.notifications(),
  });
}

export function useUnreadCount(opts: { refetchMs?: number } = {}) {
  return useQuery<NotificationCount>({
    queryKey: notificationKeys.unread,
    queryFn: () => meApi.unreadCount(),
    // The bell needs to feel live without becoming a polling
    // disaster. 30s default keeps the badge accurate without
    // spamming the api.
    refetchInterval: opts.refetchMs ?? 30_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => meApi.markRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => meApi.markAllRead(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}

// ---------- Workspace switcher ----------

export const myWorkspaceKeys = {
  all: ['me', 'workspaces'] as const satisfies QueryKey,
};

export function useMyWorkspaces() {
  return useQuery<MeWorkspace[]>({
    queryKey: myWorkspaceKeys.all,
    queryFn: () => meApi.workspaces(),
  });
}

export function useSwitchWorkspace() {
  // Caller takes the returned access_token and stores it on its own
  // (calling setTokenFromOAuth or similar). We don't invalidate other
  // queries here because the cache is workspace-scoped — the page-
  // level reload after the swap is the cleaner reset.
  return useMutation<TokenResponse, Error, { workspace_id: string }>({
    mutationFn: (payload) => authSwitchApi.switchWorkspace(payload),
  });
}

export function useCreateMyWorkspace() {
  return useMutation<CreateMyWorkspaceResponse, Error, CreateMyWorkspacePayload>({
    mutationFn: (payload) => meApi.createWorkspace(payload),
  });
}

// ---------- Priority editor ----------

export function useUpdateTaskPriority() {
  const qc = useQueryClient();
  return useMutation<Task, Error, { id: string; priority: number }>({
    mutationFn: ({ id, priority }) => tasksApi.updatePriority(id, priority),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

export function useSetMemberTeam() {
  const qc = useQueryClient();
  return useMutation<Member, Error, { memberId: string; payload: SetMemberTeamPayload }>({
    mutationFn: ({ memberId, payload }) => tenantsApi.setMemberTeam(memberId, payload),
    onSuccess: () => {
      // Member shape now carries team_id + team_role; bust the list.
      qc.invalidateQueries({ queryKey: tenantKeys.members });
    },
  });
}

export function useCreateInvite() {
  // Phase 6: create_invite now provisions the User + Member rows up
  // front, so the directory's members list is stale the moment the
  // invite is sent. Invalidate so the new entry appears without a
  // manual refresh.
  const qc = useQueryClient();
  return useMutation<InviteCreateResponse, Error, InviteCreatePayload>({
    mutationFn: (payload) => tenantsApi.createInvite(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tenantKeys.members });
    },
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
      // Agents are members too — the Directory's combined list shows
      // them alongside humans. Bust that cache so the new agent
      // appears without a manual refresh.
      qc.invalidateQueries({ queryKey: tenantKeys.members });
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

// ---------- Projects ----------

export const projectKeys = {
  all: ['projects'] as const satisfies QueryKey,
  list: (includeArchived: boolean) => ['projects', { includeArchived }] as const satisfies QueryKey,
  detail: (id: string) => ['projects', id] as const satisfies QueryKey,
  tasks: (id: string) => ['projects', id, 'tasks'] as const satisfies QueryKey,
};

export function useProjects(includeArchived = false) {
  return useQuery<Project[]>({
    queryKey: projectKeys.list(includeArchived),
    queryFn: () => projectsApi.list(includeArchived),
  });
}

export function useProject(id: string) {
  return useQuery<Project>({
    queryKey: projectKeys.detail(id),
    queryFn: () => projectsApi.get(id),
  });
}

export function useProjectTasks(id: string) {
  return useQuery<Task[]>({
    queryKey: projectKeys.tasks(id),
    queryFn: () => projectsApi.listTasks(id),
  });
}

export function useProjectHistory(id: string) {
  return useQuery<ProjectHistory>({
    queryKey: ['projects', id, 'history'],
    queryFn: () => projectsApi.history(id),
  });
}

export function useTaskActivity(id: string) {
  return useQuery<TaskActivity[]>({
    queryKey: taskKeys.activity(id),
    queryFn: () => tasksApi.listActivity(id),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation<Project, Error, CreateProjectPayload>({
    mutationFn: (payload) => projectsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation<Project, Error, UpdateProjectPayload>({
    mutationFn: (payload) => projectsApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.all });
      qc.invalidateQueries({ queryKey: projectKeys.detail(id) });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => projectsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: projectKeys.all });
      // Tasks now have project_id=null — bust the task lists too.
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

// ---------- Teams ----------

export const teamKeys = {
  all: ['teams'] as const satisfies QueryKey,
  byDepartment: (departmentId: string) =>
    ['teams', 'department', departmentId] as const satisfies QueryKey,
};

export function useTeams(departmentId?: string) {
  return useQuery<TeamRecord[]>({
    queryKey: departmentId ? teamKeys.byDepartment(departmentId) : teamKeys.all,
    queryFn: () => teamsApi.list(departmentId),
  });
}

// ---------- Departments ----------

export const departmentKeys = {
  all: ['departments'] as const satisfies QueryKey,
  list: (name?: string) =>
    (name ? (['departments', { name }] as const) : (['departments'] as const)) satisfies QueryKey,
  detail: (id: string) => ['departments', id] as const satisfies QueryKey,
};

export function useDepartments(name?: string) {
  return useQuery<Department[]>({
    queryKey: departmentKeys.list(name),
    queryFn: () => departmentsApi.list(name),
  });
}

export function useDepartment(id: string | null) {
  return useQuery<Department>({
    queryKey: departmentKeys.detail(id ?? ''),
    queryFn: () => departmentsApi.get(id as string),
    enabled: !!id,
  });
}

export function useCreateDepartment() {
  const qc = useQueryClient();
  return useMutation<Department, Error, CreateDepartmentPayload>({
    mutationFn: (payload) => departmentsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: departmentKeys.all });
    },
  });
}

export function useUpdateDepartment() {
  const qc = useQueryClient();
  return useMutation<Department, Error, { id: string; payload: UpdateDepartmentPayload }>({
    mutationFn: ({ id, payload }) => departmentsApi.update(id, payload),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: departmentKeys.all });
      qc.invalidateQueries({ queryKey: departmentKeys.detail(vars.id) });
      // Team cards show the dept name → team list cache needs a refresh.
      qc.invalidateQueries({ queryKey: teamKeys.all });
    },
  });
}

export function useDeleteDepartment() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => departmentsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: departmentKeys.all });
      // Teams that pointed at the deleted dept have their FK set to
      // null on the server — refresh the team list so the UI doesn't
      // claim a stale department label.
      qc.invalidateQueries({ queryKey: teamKeys.all });
    },
  });
}

// ---------- Cross-team requests ----------

export const requestKeys = {
  all: ['requests'] as const satisfies QueryKey,
  forTask: (id: string) => ['requests', 'task', id] as const satisfies QueryKey,
  inbox: (teamId: string, status?: RequestStatus) =>
    ['requests', 'team', teamId, status ?? 'ALL'] as const satisfies QueryKey,
};

export function useTaskRequests(taskId: string) {
  return useQuery<TaskRequest[]>({
    queryKey: requestKeys.forTask(taskId),
    queryFn: () => tasksApi.listRequests(taskId),
  });
}

export function useTeamInboxRequests(teamId: string, status: RequestStatus = 'PENDING') {
  return useQuery<TaskRequest[]>({
    queryKey: requestKeys.inbox(teamId, status),
    queryFn: () => requestsApi.listInbox(teamId, status),
    enabled: !!teamId,
    refetchInterval: 30_000,
  });
}

export function useCreateTaskRequest(taskId: string) {
  const qc = useQueryClient();
  return useMutation<TaskRequest, Error, CreateRequestPayload>({
    mutationFn: (payload) => tasksApi.createRequest(taskId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: requestKeys.forTask(taskId) });
      qc.invalidateQueries({ queryKey: requestKeys.all });
    },
  });
}

export function useFulfillRequest(requestId: string) {
  const qc = useQueryClient();
  return useMutation<TaskRequest, Error, FulfillRequestPayload>({
    mutationFn: (payload) => requestsApi.fulfill(requestId, payload),
    onSuccess: () => {
      // Fulfill creates a brand new task + a BLOCKS relation, so the
      // task list, relations cache, and request inbox all get a refresh.
      qc.invalidateQueries({ queryKey: requestKeys.all });
      qc.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

export function useRejectRequest(requestId: string) {
  const qc = useQueryClient();
  return useMutation<TaskRequest, Error, RejectRequestPayload>({
    mutationFn: (payload) => requestsApi.reject(requestId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: requestKeys.all });
    },
  });
}

export function useCreateTeam() {
  const qc = useQueryClient();
  return useMutation<TeamRecord, Error, CreateTeamPayload>({
    mutationFn: (payload) => teamsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: teamKeys.all });
    },
  });
}

export function useUpdateTeam() {
  const qc = useQueryClient();
  return useMutation<TeamRecord, Error, { id: string; payload: UpdateTeamPayload }>({
    mutationFn: ({ id, payload }) => teamsApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: teamKeys.all });
      // Member-team labels surface team names — bust the directory list too.
      qc.invalidateQueries({ queryKey: tenantKeys.members });
    },
  });
}

export function useDeleteTeam() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => teamsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: teamKeys.all });
      // Members previously on the team go to "no team" — refresh the
      // directory so the side panel doesn't show stale assignments.
      qc.invalidateQueries({ queryKey: tenantKeys.members });
    },
  });
}

// ---------- Task project / team move ----------

export function useUpdateTaskLinks(id: string) {
  const qc = useQueryClient();
  return useMutation<Task, Error, UpdateTaskLinksPayload>({
    mutationFn: (payload) => tasksApi.updateLinks(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: taskKeys.all });
      qc.invalidateQueries({ queryKey: taskKeys.detail(id) });
      // Also bust project-scoped task lists since the row may have
      // moved between projects.
      qc.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

// ---------- Audit logs ----------

export const auditKeys = {
  all: ['audit', 'logs'] as const satisfies QueryKey,
};

export function useAuditLogs(opts: { limit?: number } = {}) {
  return useQuery<AuditLog[]>({
    queryKey: opts.limit ? (['audit', 'logs', { limit: opts.limit }] as const) : auditKeys.all,
    queryFn: () => auditApi.list(opts),
    // 30s refetch keeps the audit feel live without polling at a
    // disaster cadence — admins watching for a spike of suspensions
    // see new rows on a slow tick.
    refetchInterval: 30_000,
  });
}
