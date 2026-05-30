'use client';

// Superadmin tenant-user editor.
//
// Fields:
//  - Team + team_role (mutually exclusive with the Head appointment).
//  - Department (head appointment) — picking a dept here promotes
//    the user to head of it; the backend clears their team_id and
//    team_role per the Round-2 isolation rule.
//  - The form refuses to submit both a non-null team_id AND a non-
//    null department_id at the same time; the server enforces the
//    same rule with 400 as a belt to this brace.
//
// The Manager / Lead replacement warning is best-effort client-side
// hint: if we know the target team already has a sitting MANAGER (or
// LEAD) we mention them by name and require an explicit confirm
// before sending the PATCH. The server's transactional demotion
// still runs regardless — the warning is purely to make the
// destructive shape visible.

import { useEffect, useMemo, useState } from 'react';

import {
  ApiError,
  type AdminWorkspaceUserRow,
  type PatchWorkspaceUserPayload,
  type TeamRoleValue,
} from '../lib/api';
import { usePatchWorkspaceUser, useWorkspaceUsers } from '../lib/queries';

interface TeamOption {
  id: string;
  name: string;
}

interface DepartmentOption {
  id: string;
  name: string;
}

export function EditWorkspaceUserDialog({
  workspaceId,
  user,
  teamOptions,
  departmentOptions,
  onClose,
}: {
  workspaceId: string;
  user: AdminWorkspaceUserRow;
  teamOptions: TeamOption[];
  departmentOptions: DepartmentOption[];
  onClose: () => void;
}) {
  // The picker forms a tiny state machine. ``intent`` controls which
  // branch the form is shaping the payload around:
  //   - 'team'  → team_id + team_role; department_id is forced null
  //     (clears any head appointment).
  //   - 'head'  → department_id; team_id + team_role forced null.
  //   - 'none'  → both null (unassign entirely).
  type Intent = 'team' | 'head' | 'none';
  const [intent, setIntent] = useState<Intent>(
    user.headed_department_id != null ? 'head' : user.team_id != null ? 'team' : 'none',
  );
  const [teamId, setTeamId] = useState<string>(user.team_id ?? '');
  const [teamRole, setTeamRole] = useState<TeamRoleValue>(user.team_role ?? 'MEMBER');
  const [departmentId, setDepartmentId] = useState<string>(user.headed_department_id ?? '');
  const [confirmReplace, setConfirmReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = usePatchWorkspaceUser(workspaceId);

  // Used purely to surface the "replacing X" warning. We list a single
  // page (50 rows) which is enough on local installs; for hot tenants
  // we'd swap this for a dedicated /teams/{id}/leadership lookup.
  const { data: usersPage } = useWorkspaceUsers(workspaceId, { limit: 200 });
  const allUsers = usersPage?.items ?? [];

  // Reset state when the dialog is reused for a different user.
  useEffect(() => {
    setIntent(user.headed_department_id != null ? 'head' : user.team_id != null ? 'team' : 'none');
    setTeamId(user.team_id ?? '');
    setTeamRole(user.team_role ?? 'MEMBER');
    setDepartmentId(user.headed_department_id ?? '');
    setConfirmReplace(false);
    setError(null);
  }, [user.member_id, user.team_id, user.team_role, user.headed_department_id]);

  // Sitting MANAGER/LEAD on the chosen team, excluding the user we're
  // editing. Drives the destructive warning + confirm gate.
  const sittingHolder = useMemo(() => {
    if (intent !== 'team' || teamId === '') return null;
    if (teamRole !== 'MANAGER' && teamRole !== 'LEAD') return null;
    return (
      allUsers.find(
        (u) => u.member_id !== user.member_id && u.team_id === teamId && u.team_role === teamRole,
      ) ?? null
    );
  }, [intent, teamId, teamRole, allUsers, user.member_id]);

  const submit = async () => {
    setError(null);
    const payload: PatchWorkspaceUserPayload = {};
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
    if (sittingHolder && !confirmReplace) {
      setError(
        `Team already has a ${teamRole} (${sittingHolder.full_name}). ` +
          'Confirm the demotion below to continue.',
      );
      return;
    }
    try {
      await mutation.mutateAsync({ userId: user.user_id, payload });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Patch failed');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={() => {
        if (!mutation.isPending) onClose();
      }}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-slate-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-900">Edit hierarchy slot</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {user.full_name}
            {user.email ? ` · ${user.email}` : ''}
          </p>
        </header>

        <div className="space-y-4 px-5 py-4">
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
            <p className="mt-2 text-[11px] italic text-slate-500">
              Head + Team are mutually exclusive — picking Head clears their team assignment;
              picking Team clears headship.
            </p>
          </div>

          {intent === 'team' ? (
            <>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Team
                </label>
                <select
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
              </div>
              {teamId !== '' ? (
                <div>
                  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Team role
                  </label>
                  <select
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
                    <span className="font-mono">{sittingHolder.full_name}</span>). Confirm to demote
                    them to MEMBER in the same transaction.
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
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Department to head
              </label>
              <select
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
              <p className="mt-2 text-[11px] italic text-slate-500">
                If they were already on a team, their team_id and team_role will be cleared to null
                (Round-2 isolation rule).
              </p>
            </div>
          ) : null}

          {intent === 'none' ? (
            <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
              Unassign — removes them from any team and from heading any department. They&apos;ll
              remain a workspace member with their existing workspace role.
            </p>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={mutation.isPending}
            className="rounded-md bg-rose-700 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {mutation.isPending ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </div>
    </div>
  );
}
