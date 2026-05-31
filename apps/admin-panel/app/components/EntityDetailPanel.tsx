'use client';

// Canonical detail / edit surface for the admin-panel. ONE body, ONE
// set of sections — the entry mode just decides how the workspace
// context is established and which sections apply:
//
// - { kind: 'user', userId }                   opened from /users
// - { kind: 'workspace-member', workspaceId, memberId }
//                                              opened from /workspaces/[id]
//                                              or from an agent row in /users
//
// Sections rendered (when applicable):
//
//   1. Identity header
//   2. Workspaces + Global ban + Force password reset  (HUMAN only)
//   3. Active workspace picker                          (multi-ws human in user mode)
//   4. Profile (workspace_role + priority)              (workspace context required)
//   5. Hierarchy slot (team + dept head)                (workspace context required)
//   6. Activity stats                                   (workspace context required)
//
// Agents skip section 2 entirely — they have no global user identity
// to ban / reset / list memberships for.
//
// All data is fetched inside the panel via the standard query hooks,
// so callers pass just IDs. The workspace listing fetched here
// re-uses the workspaces drill-down page's cache (same query key),
// so opening the panel from there is effectively free.

import { useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  type AdminUserDetail,
  type AdminWorkspaceUserRow,
  type ForcePasswordResetResponse,
  type PatchWorkspaceMemberPayload,
  type TeamRoleValue,
  type WorkspaceRole,
} from '../lib/api';
import {
  useAdminUser,
  useForcePasswordReset,
  useMemberStats,
  usePatchWorkspaceMember,
  useSetUserBanned,
  useWorkspaceMember,
  useWorkspaceUsers,
} from '../lib/queries';

type Entry =
  | { kind: 'user'; userId: string }
  | { kind: 'workspace-member'; workspaceId: string; memberId: string };

interface RBAC {
  canEdit: boolean;
  disabledReason?: string;
}

// Sentinel for "operator hasn't typed a priority value" — see
// onSave + dirty derivation. 0 isn't a valid priority (range 1..100)
// so it's safe as a sentinel.
const PRIORITY_SENTINEL = 0;

// Cap the workspace-listing fetch at a sane page size for option
// derivation. Tenants with thousands of members would want a dedicated
// /admin/teams + /admin/departments listing; that's a deferred follow-up.
const WORKSPACE_LISTING_LIMIT = 200;

export function EntityDetailPanel({
  entry,
  rbac = { canEdit: true },
  onClose,
}: {
  entry: Entry;
  rbac?: RBAC;
  onClose: () => void;
}) {
  // ----- Resolve the active workspace context -----
  // Workspace-member entry: IDs come straight from the entry.
  // User entry: the operator picks (or auto-picks the only one).
  const [pickedWsId, setPickedWsId] = useState<string | null>(null);

  // Global-user data (humans only). For workspace-member entry we
  // resolve userId AFTER fetching the member row.
  const directUserId = entry.kind === 'user' ? entry.userId : null;
  const userQuery = useAdminUser(directUserId);

  // For user-entry, default the active workspace to the first
  // membership the moment user data lands.
  useEffect(() => {
    if (entry.kind !== 'user') return;
    if (pickedWsId !== null) return;
    const first = userQuery.data?.memberships[0]?.workspace_id ?? null;
    if (first) setPickedWsId(first);
  }, [entry.kind, userQuery.data, pickedWsId]);

  const activeWsId = entry.kind === 'workspace-member' ? entry.workspaceId : pickedWsId;
  const activeMemberId =
    entry.kind === 'workspace-member'
      ? entry.memberId
      : (userQuery.data?.memberships.find((m) => m.workspace_id === activeWsId)?.member_id ?? null);

  const memberQuery = useWorkspaceMember(activeWsId, activeMemberId);
  const member = memberQuery.data;

  // For workspace-member entry, the global-user data only exists for
  // humans (agents have no user_id). Fetch it lazily once we know.
  const memberUserId = entry.kind === 'workspace-member' && member?.user_id ? member.user_id : null;
  const memberUserQuery = useAdminUser(memberUserId);
  const user = entry.kind === 'user' ? userQuery.data : memberUserQuery.data;

  // Workspace-scoped listing — feeds team/dept option derivation +
  // the sitting-MANAGER warning. Shared query key with the drill-down
  // page, so no duplicate fetch when the panel opens from there.
  const usersListQuery = useWorkspaceUsers(activeWsId, { limit: WORKSPACE_LISTING_LIMIT });
  const allMembers = usersListQuery.data?.items ?? [];

  const isAgent = member?.type === 'AGENT';
  const showGlobalSection = !!user && !isAgent;

  return (
    <DialogFrame onClose={onClose}>
      <IdentityHeader
        member={member}
        user={user}
        fallbackTitle={entry.kind === 'user' ? 'User' : 'Member'}
      />

      {showGlobalSection && user ? <GlobalUserSections user={user} onClose={onClose} /> : null}

      {/* Active workspace picker — only when the operator entered
          through /users AND has more than one membership. The picker
          changes the workspace-scoped queries below. */}
      {entry.kind === 'user' && (userQuery.data?.memberships.length ?? 0) > 1 ? (
        <Section title="Active workspace">
          <label htmlFor="edp_ws" className="sr-only">
            Active workspace
          </label>
          <select
            id="edp_ws"
            aria-label="Active workspace"
            value={activeWsId ?? ''}
            onChange={(e) => setPickedWsId(e.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
          >
            {userQuery.data!.memberships.map((m) => (
              <option key={m.workspace_id} value={m.workspace_id}>
                {m.workspace_name} ({m.role.replace('WORKSPACE_', '')})
              </option>
            ))}
          </select>
        </Section>
      ) : null}

      {/* Workspace-scoped sections. Always rendered when we have a
          member row resolved — same surface for both entry kinds. */}
      {member && activeWsId ? (
        <WorkspaceScopedSections
          workspaceId={activeWsId}
          member={member}
          allMembers={allMembers}
          rbac={rbac}
        />
      ) : memberQuery.isLoading ? (
        <Section title="Workspace context">
          <p className="text-xs text-slate-500">Loading workspace slot…</p>
        </Section>
      ) : null}

      <footer className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Close
        </button>
      </footer>
    </DialogFrame>
  );
}

// ---------- shared frame ----------

function DialogFrame({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-100 px-5 py-4 last:border-b-0">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </h3>
      {children}
    </section>
  );
}

// ---------- identity ----------

function IdentityHeader({
  member,
  user,
  fallbackTitle,
}: {
  member: AdminWorkspaceUserRow | undefined;
  user: AdminUserDetail | undefined;
  fallbackTitle: string;
}) {
  // Prefer the workspace-scoped row when we have one (it carries the
  // type pill + workspace role). Fall back to the global user shape
  // when the panel was opened from /users and the workspace member
  // isn't resolved yet.
  const title = member?.full_name ?? user?.full_name ?? fallbackTitle;
  const email = member?.email ?? user?.email ?? null;
  const type = member?.type;
  return (
    <header className="border-b border-slate-200 px-5 py-4">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {type ? (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
            {type}
          </span>
        ) : null}
        {user?.is_superadmin ? (
          <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-rose-800">
            Superadmin
          </span>
        ) : null}
        {user?.is_banned ? (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
            Banned
          </span>
        ) : null}
        {member?.is_suspended ? (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            Suspended
          </span>
        ) : null}
      </div>
      {email ? <p className="text-xs text-slate-500">{email}</p> : null}
      {user ? (
        <p className="mt-1 text-[11px] text-slate-500">
          User since {new Date(user.created_at).toLocaleString()}
          {user.sessions_invalidated_at
            ? ` · sessions killed ${new Date(user.sessions_invalidated_at).toLocaleString()}`
            : ''}
        </p>
      ) : null}
    </header>
  );
}

// ---------- global-user sections (HUMAN only) ----------

function GlobalUserSections({
  user,
  onClose: _onClose,
}: {
  user: AdminUserDetail;
  onClose: () => void;
}) {
  const banMutation = useSetUserBanned();
  const resetMutation = useForcePasswordReset();
  const [confirm, setConfirm] = useState<'ban' | 'unban' | null>(null);
  const [typedEmail, setTypedEmail] = useState('');
  const [resetPreview, setResetPreview] = useState<ForcePasswordResetResponse | null>(null);
  const [opError, setOpError] = useState<string | null>(null);

  useEffect(() => {
    setConfirm(null);
    setTypedEmail('');
    setResetPreview(null);
    setOpError(null);
  }, [user.id]);

  const pending = banMutation.isPending || resetMutation.isPending;

  const onConfirmBan = async () => {
    if (!confirm) return;
    setOpError(null);
    try {
      await banMutation.mutateAsync({
        userId: user.id,
        payload: { is_banned: confirm === 'ban' },
      });
      setConfirm(null);
      setTypedEmail('');
    } catch (err) {
      setOpError(err instanceof ApiError ? err.detail : 'Action failed');
    }
  };

  const onForceReset = async () => {
    setOpError(null);
    try {
      const out = await resetMutation.mutateAsync({ userId: user.id });
      setResetPreview(out);
    } catch (err) {
      setOpError(err instanceof ApiError ? err.detail : 'Action failed');
    }
  };

  return (
    <>
      <Section title="Workspaces">
        {user.memberships.length === 0 ? (
          <p className="text-xs italic text-slate-500">
            This user has no active workspace memberships.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-1 text-left">Workspace</th>
                <th className="py-1 text-left">Slug</th>
                <th className="py-1 text-left">Role</th>
                <th className="py-1 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {user.memberships.map((m) => (
                <tr key={m.member_id}>
                  <td className="truncate py-1.5 font-medium text-slate-900">{m.workspace_name}</td>
                  <td className="py-1.5 font-mono text-[11px] text-slate-500">
                    {m.workspace_slug}
                  </td>
                  <td className="py-1.5 text-slate-700">{m.role.replace('WORKSPACE_', '')}</td>
                  <td className="py-1.5">
                    {m.is_suspended ? (
                      <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                        Suspended
                      </span>
                    ) : (
                      <span className="text-[11px] text-emerald-700">Active</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Global ban">
        {user.is_superadmin ? (
          <p className="text-xs italic text-slate-500">
            Superadmins cannot be banned via this surface. Revoke their flag via{' '}
            <span className="font-mono">scripts/make_superadmin --revoke</span> first.
          </p>
        ) : confirm === null ? (
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-slate-600">
              {user.is_banned
                ? 'This user is currently banned platform-wide. Restoring re-enables access immediately.'
                : 'Bans take effect on the next request; every workspace returns 403.'}
            </p>
            {user.is_banned ? (
              <button
                type="button"
                onClick={() => setConfirm('unban')}
                disabled={pending}
                className="rounded-md border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
              >
                Restore access
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setConfirm('ban')}
                disabled={pending}
                className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
              >
                Ban user
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3 rounded-md border border-red-200 bg-red-50/60 p-3">
            {confirm === 'ban' ? (
              <>
                <p className="text-sm text-red-900">
                  Type <span className="font-mono">{user.email}</span> to confirm the ban. This will
                  block every authenticated request the user makes, across every workspace, until
                  restored.
                </p>
                <input
                  type="text"
                  value={typedEmail}
                  onChange={(e) => setTypedEmail(e.target.value)}
                  autoComplete="off"
                  autoFocus
                  className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
                />
              </>
            ) : (
              <p className="text-sm text-emerald-900">
                Restoring access for <span className="font-mono">{user.email}</span> takes effect on
                their next request. No further confirmation needed.
              </p>
            )}
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setConfirm(null);
                  setTypedEmail('');
                }}
                disabled={pending}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onConfirmBan}
                disabled={pending || (confirm === 'ban' && typedEmail.trim() !== user.email)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50 ${
                  confirm === 'ban'
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {pending ? 'Working…' : confirm === 'ban' ? 'Ban user' : 'Restore access'}
              </button>
            </div>
          </div>
        )}
      </Section>

      <Section title="Force password reset">
        {resetPreview ? (
          <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <p className="font-semibold">Simulated recovery email (logged to api):</p>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded border border-amber-200 bg-white p-2 font-mono text-[11px]">
              {resetPreview.simulated_email}
            </pre>
            <p>
              Sessions invalidated at{' '}
              <span className="font-mono">
                {new Date(resetPreview.sessions_invalidated_at).toLocaleString()}
              </span>
              . Existing JWTs now bounce with 401.
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-slate-600">
              Randomises the password hash AND invalidates every outstanding JWT — the user must run
              the recovery flow to regain access. Email delivery is simulated in this stage;
              we&apos;ll show you the preview below.
            </p>
            <button
              type="button"
              onClick={onForceReset}
              disabled={pending}
              className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-60"
            >
              Force reset
            </button>
          </div>
        )}
      </Section>

      {opError ? (
        <p role="alert" className="px-5 pb-3 text-sm text-red-600">
          {opError}
        </p>
      ) : null}
    </>
  );
}

// ---------- workspace-scoped sections (always) ----------

function WorkspaceScopedSections({
  workspaceId,
  member,
  allMembers,
  rbac,
}: {
  workspaceId: string;
  member: AdminWorkspaceUserRow;
  allMembers: AdminWorkspaceUserRow[];
  rbac: RBAC;
}) {
  const [editing, setEditing] = useState(false);
  const mutation = usePatchWorkspaceMember(workspaceId);
  const { data: stats } = useMemberStats(workspaceId, member.member_id);

  type Intent = 'team' | 'head' | 'none';
  const initialIntent: Intent =
    member.headed_department_id != null ? 'head' : member.team_id != null ? 'team' : 'none';

  const [intent, setIntent] = useState<Intent>(initialIntent);
  const [teamId, setTeamId] = useState<string>(member.team_id ?? '');
  const [teamRole, setTeamRole] = useState<TeamRoleValue>(member.team_role ?? 'MEMBER');
  const [departmentId, setDepartmentId] = useState<string>(member.headed_department_id ?? '');
  const [workspaceRole, setWorkspaceRole] = useState<WorkspaceRole>(member.role);
  const [priority, setPriority] = useState<number>(PRIORITY_SENTINEL);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Snap form state back to persisted values whenever the active
  // member changes (e.g. workspace picker swapped to a different
  // workspace, or a refetch landed new data).
  useEffect(() => {
    setIntent(
      member.headed_department_id != null ? 'head' : member.team_id != null ? 'team' : 'none',
    );
    setTeamId(member.team_id ?? '');
    setTeamRole(member.team_role ?? 'MEMBER');
    setDepartmentId(member.headed_department_id ?? '');
    setWorkspaceRole(member.role);
    setPriority(PRIORITY_SENTINEL);
    setConfirmReplace(false);
    setError(null);
    setEditing(false);
  }, [
    member.member_id,
    member.team_id,
    member.team_role,
    member.headed_department_id,
    member.role,
  ]);

  const teamOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of allMembers) {
      if (u.team_id && u.team_name) map.set(u.team_id, u.team_name);
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [allMembers]);

  const departmentOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const u of allMembers) {
      if (u.team_department_id && u.team_department_name) {
        map.set(u.team_department_id, u.team_department_name);
      }
      if (u.headed_department_id && u.headed_department_name) {
        map.set(u.headed_department_id, u.headed_department_name);
      }
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [allMembers]);

  const sittingHolder = useMemo(() => {
    if (intent !== 'team' || teamId === '') return null;
    if (teamRole !== 'MANAGER' && teamRole !== 'LEAD') return null;
    return (
      allMembers.find(
        (m) => m.member_id !== member.member_id && m.team_id === teamId && m.team_role === teamRole,
      ) ?? null
    );
  }, [intent, teamId, teamRole, allMembers, member.member_id]);

  const dirty = useMemo(() => {
    if (intent !== initialIntent) return true;
    if (intent === 'team') {
      if (teamId !== (member.team_id ?? '')) return true;
      if (teamId !== '' && teamRole !== (member.team_role ?? 'MEMBER')) return true;
    }
    if (intent === 'head' && departmentId !== (member.headed_department_id ?? '')) return true;
    if (workspaceRole !== member.role) return true;
    if (priority !== PRIORITY_SENTINEL) return true;
    return false;
  }, [intent, initialIntent, teamId, teamRole, departmentId, workspaceRole, priority, member]);

  const onCancel = () => {
    setIntent(initialIntent);
    setTeamId(member.team_id ?? '');
    setTeamRole(member.team_role ?? 'MEMBER');
    setDepartmentId(member.headed_department_id ?? '');
    setWorkspaceRole(member.role);
    setPriority(PRIORITY_SENTINEL);
    setConfirmReplace(false);
    setError(null);
    setEditing(false);
  };

  const onSave = async () => {
    setError(null);
    const payload: PatchWorkspaceMemberPayload = {};
    if (intent !== initialIntent || intent === 'team') {
      if (intent === 'team') {
        payload.team_id = teamId === '' ? null : teamId;
        payload.team_role = teamId === '' ? null : teamRole;
        payload.department_id = null;
      } else if (intent === 'head') {
        if (departmentId === '') {
          setError('Pick a department to promote this user to head.');
          return;
        }
        payload.department_id = departmentId;
        payload.team_id = null;
        payload.team_role = null;
      } else {
        payload.team_id = null;
        payload.team_role = null;
        payload.department_id = null;
      }
    }
    if (workspaceRole !== member.role) payload.workspace_role = workspaceRole;
    if (priority !== PRIORITY_SENTINEL) payload.priority = priority;
    if (sittingHolder && !confirmReplace) {
      setError(
        `Team already has a ${teamRole} (${sittingHolder.full_name}). ` +
          'Confirm the demotion below to continue.',
      );
      return;
    }
    try {
      await mutation.mutateAsync({ memberId: member.member_id, payload });
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Patch failed');
    }
  };

  return (
    <>
      <Section title="Workspace slot">
        <div className="flex items-start justify-between gap-3">
          <dl className="space-y-1 text-sm">
            <Row label="Workspace role">{member.role.replace('WORKSPACE_', '')}</Row>
          </dl>
          <EditToolbar
            editing={editing}
            canEdit={rbac.canEdit}
            disabledReason={rbac.disabledReason}
            dirty={dirty}
            saving={mutation.isPending}
            onEdit={() => setEditing(true)}
            onCancel={onCancel}
            onSave={onSave}
          />
        </div>
        {editing ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="edp_role"
                className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
              >
                Workspace role
              </label>
              <select
                id="edp_role"
                value={workspaceRole}
                onChange={(e) => setWorkspaceRole(e.target.value as WorkspaceRole)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              >
                <option value="WORKSPACE_OWNER">WORKSPACE_OWNER</option>
                <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN</option>
                <option value="WORKSPACE_USER">WORKSPACE_USER</option>
              </select>
            </div>
            <div>
              <label
                htmlFor="edp_priority"
                className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
              >
                Priority
              </label>
              <input
                id="edp_priority"
                type="number"
                min={1}
                max={100}
                value={priority === PRIORITY_SENTINEL ? '' : priority}
                placeholder="1..100"
                onChange={(e) => {
                  const n = Number(e.target.value);
                  setPriority(Number.isFinite(n) && n >= 1 && n <= 100 ? n : PRIORITY_SENTINEL);
                }}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
              <p className="mt-1 text-[10px] italic text-slate-500">
                Leave blank to keep the current rank. 1 = highest.
              </p>
            </div>
          </div>
        ) : null}
      </Section>

      <Section title="Hierarchy slot">
        {editing ? (
          <div className="space-y-4">
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Assign as
              </p>
              <div className="grid grid-cols-3 gap-2">
                {(['team', 'head', 'none'] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setIntent(value)}
                    className={`rounded-md border px-3 py-2 text-sm transition ${
                      intent === value
                        ? 'border-rose-400 bg-rose-50 font-semibold text-rose-800'
                        : 'border-slate-200 text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    {value === 'team'
                      ? 'Team member'
                      : value === 'head'
                        ? 'Department head'
                        : 'Unassigned'}
                  </button>
                ))}
              </div>
            </div>
            {intent === 'team' ? (
              <>
                <div>
                  <label
                    htmlFor="edp_team"
                    className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                  >
                    Team
                  </label>
                  {teamOptions.length > 0 ? (
                    <select
                      id="edp_team"
                      value={teamId}
                      onChange={(e) => setTeamId(e.target.value)}
                      className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
                    >
                      <option value="">— Unassign —</option>
                      {teamOptions.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id="edp_team"
                      type="text"
                      value={teamId}
                      onChange={(e) => setTeamId(e.target.value)}
                      placeholder="team UUID"
                      className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
                    />
                  )}
                </div>
                {teamId !== '' ? (
                  <div>
                    <label
                      htmlFor="edp_team_role"
                      className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                    >
                      Team role
                    </label>
                    <select
                      id="edp_team_role"
                      value={teamRole}
                      onChange={(e) => setTeamRole(e.target.value as TeamRoleValue)}
                      className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
                    >
                      <option value="MANAGER">MANAGER</option>
                      <option value="LEAD">LEAD</option>
                      <option value="MEMBER">MEMBER</option>
                    </select>
                  </div>
                ) : null}
                {sittingHolder ? (
                  <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                    <p>
                      This team already has a <strong>{teamRole}</strong> (
                      <span className="font-mono">{sittingHolder.full_name}</span>). Confirm to
                      demote them to MEMBER in the same transaction.
                    </p>
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={confirmReplace}
                        onChange={(e) => setConfirmReplace(e.target.checked)}
                      />
                      Yes, replace the current {teamRole}
                    </label>
                  </div>
                ) : null}
              </>
            ) : null}
            {intent === 'head' ? (
              <div>
                <label
                  htmlFor="edp_dept"
                  className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500"
                >
                  Department to head
                </label>
                {departmentOptions.length > 0 ? (
                  <select
                    id="edp_dept"
                    value={departmentId}
                    onChange={(e) => setDepartmentId(e.target.value)}
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="">— Pick a department —</option>
                    {departmentOptions.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="edp_dept"
                    type="text"
                    value={departmentId}
                    onChange={(e) => setDepartmentId(e.target.value)}
                    placeholder="department UUID"
                    className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
                  />
                )}
              </div>
            ) : null}
            {intent === 'none' ? (
              <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                Unassign — removes them from any team and from heading any department.
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            ) : null}
          </div>
        ) : (
          <dl className="space-y-1 text-sm">
            <Row label="Team">
              {member.team_name ? (
                <>
                  {member.team_name} <span className="text-slate-500">({member.team_role})</span>
                </>
              ) : (
                <span className="italic text-slate-400">Unassigned</span>
              )}
            </Row>
            <Row label="Department (via team)">
              {member.team_department_name ?? <span className="italic text-slate-400">—</span>}
            </Row>
            <Row label="Heads department">
              {member.headed_department_name ?? <span className="italic text-slate-400">—</span>}
            </Row>
          </dl>
        )}
      </Section>

      <Section title="Activity">
        {stats ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Assigned" value={stats.assigned_count} />
            <StatCard label="Completed" value={stats.completed_count} />
            <StatCard label="Tokens used" value={stats.total_tokens_used} />
            <StatCard
              label="Avg resolution"
              value={
                stats.avg_resolution_seconds != null
                  ? `${Math.round(stats.avg_resolution_seconds)}s`
                  : '—'
              }
            />
            <StatCard
              label="Accuracy"
              value={stats.accuracy_percent != null ? `${stats.accuracy_percent.toFixed(1)}` : '—'}
            />
            <StatCard
              label="Last activity"
              value={
                stats.last_activity_at ? new Date(stats.last_activity_at).toLocaleDateString() : '—'
              }
            />
          </div>
        ) : (
          <p className="text-xs italic text-slate-500">Loading activity…</p>
        )}
      </Section>
    </>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3">
      <dt className="w-44 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className="text-sm text-slate-800">{children}</dd>
    </div>
  );
}

// ---------- EditToolbar ----------

interface EditToolbarProps {
  editing: boolean;
  canEdit: boolean;
  disabledReason?: string;
  dirty: boolean;
  saving: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void | Promise<void>;
}

function EditToolbar({
  editing,
  canEdit,
  disabledReason,
  dirty,
  saving,
  onEdit,
  onCancel,
  onSave,
}: EditToolbarProps) {
  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void onSave()}
          disabled={saving || !dirty}
          className="rounded-md bg-rose-700 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onEdit}
      disabled={!canEdit}
      title={!canEdit ? disabledReason : undefined}
      className="rounded-md border border-rose-200 bg-white px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
    >
      Edit
    </button>
  );
}
