// Client-side mirror of the api's priority-gated reach checks (see
// app/api/deps.py — require_admin_priority_le). The api is still the
// authority — these helpers only drive UI affordances (showing or
// hiding the Edit button, computing the "ask X" hint on the disabled
// state). Every action still goes through the api, which 403s on its
// own if a forged client somehow re-enables the button.

import type { Department, Member, MemberDepartmentSummary, TeamRecord } from './api';
import type { CurrentPrincipal } from './auth';

/** Department CRUD requires priority ≤ 2 (mirrors DepartmentReachDep). */
export const DEPARTMENT_REACH_PRIORITY = 2;

/** Team CRUD requires priority ≤ 3 (mirrors TeamReachDep). */
export const TEAM_REACH_PRIORITY = 3;

function isAdminRole(principal: CurrentPrincipal | null): boolean {
  return principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';
}

function withinReach(principal: CurrentPrincipal | null, maxPriority: number): boolean {
  if (!principal) return false;
  // Owner always passes — matches the api's convention (priority 1 by
  // default, but even a re-prioritised owner keeps reach).
  if (principal.role === 'WORKSPACE_OWNER') return true;
  if (principal.role !== 'WORKSPACE_ADMIN') return false;
  return principal.priority <= maxPriority;
}

export function canEditDepartment(principal: CurrentPrincipal | null): boolean {
  return withinReach(principal, DEPARTMENT_REACH_PRIORITY);
}

export function canEditTeam(principal: CurrentPrincipal | null): boolean {
  return withinReach(principal, TEAM_REACH_PRIORITY);
}

export function canEditMember(principal: CurrentPrincipal | null): boolean {
  return isAdminRole(principal);
}

export function canEditProject(principal: CurrentPrincipal | null): boolean {
  return isAdminRole(principal);
}

/** Resolve the nearest authorised editors so the disabled-state tooltip
 *  can name names. The team's MANAGER is always the closest; the
 *  Department Head sits one rung above. Falls back to a generic ask
 *  when neither is set (very early in a workspace's life, or a project
 *  that isn't team-scoped). */
export interface NearestEditors {
  teamManager: Member | null;
  departmentHead: Member | null;
}

export function nearestEditors(opts: {
  teamId?: string | null;
  departmentId?: string | null;
  members: Member[];
  departments: Department[];
  teams?: TeamRecord[];
}): NearestEditors {
  const { teamId, departmentId, members, departments, teams = [] } = opts;
  const teamManager =
    teamId != null
      ? (members.find((m) => m.team_id === teamId && m.team_role === 'MANAGER') ?? null)
      : null;

  // Department: prefer explicit, fall back to derived-from-team.
  const deptId =
    departmentId ??
    (teamId != null ? (teams.find((t) => t.id === teamId)?.department_id ?? null) : null);
  const dept = deptId != null ? (departments.find((d) => d.id === deptId) ?? null) : null;
  const departmentHead =
    dept?.head_id != null ? (members.find((m) => m.id === dept.head_id) ?? null) : null;

  return { teamManager, departmentHead };
}

/** Build the human-readable "ask X" sentence rendered on the disabled
 *  Edit button's tooltip. Lists whichever of (Team Manager, Department
 *  Head) is actually known; falls back to a generic ask when neither
 *  exists yet. */
export function disabledEditTooltip(editors: NearestEditors): string {
  const parts: string[] = [];
  if (editors.teamManager) parts.push(`your Team Manager (${editors.teamManager.name})`);
  if (editors.departmentHead) parts.push(`Department Head (${editors.departmentHead.name})`);

  const prefix = 'You do not have permission to edit this.';
  if (parts.length === 0) {
    return `${prefix} Please ask a workspace admin.`;
  }
  return `${prefix} Please ask ${parts.join(' or ')}.`;
}

/** Convenience wrapper: resolve the nearest editor for a department's
 *  own scope. Only the Department Head is meaningful here (no team
 *  scope above it); the message still falls back to "ask a workspace
 *  admin" when the head is unset. */
export function disabledDepartmentEditTooltip(department: {
  head?: MemberDepartmentSummary | { id: string; name: string } | null;
  head_id?: string | null;
}): string {
  const headName = department.head && 'name' in department.head ? department.head.name : null;
  const prefix = 'You do not have permission to edit this.';
  if (headName) {
    return `${prefix} Please ask the Department Head (${headName}).`;
  }
  return `${prefix} Please ask a workspace admin with priority ≤ ${DEPARTMENT_REACH_PRIORITY}.`;
}
