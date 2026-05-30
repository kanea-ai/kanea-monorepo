'use client';

// Specialised confirmation modal for the single-MANAGER / single-LEAD
// rule. When an admin tries to assign a MANAGER (or LEAD) on a team
// that already has one, the save action is intercepted client-side so
// the admin sees explicitly who they're about to displace BEFORE the
// PATCH leaves the browser. The server enforces the same invariant
// (see InviteService.set_member_team) — this modal is the courteous
// UI layer on top.

import type { Member, TeamRole } from '../lib/api';
import { ConfirmDialog } from './ConfirmDialog';

export interface RoleReplacementContext {
  teamName: string;
  /** Either MANAGER or LEAD — the constraint doesn't apply to MEMBER. */
  role: Extract<TeamRole, 'MANAGER' | 'LEAD'>;
  /** The member currently holding ``role`` on the team. They will be
   *  demoted to MEMBER in the same DB transaction. */
  sittingHolder: Member;
  newHolderName: string;
}

export function RoleReplacementConfirm({
  context,
  pending,
  onConfirm,
  onCancel,
}: {
  context: RoleReplacementContext | null;
  pending: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}) {
  const open = context !== null;
  const roleLabel = context?.role === 'MANAGER' ? 'Manager' : 'Lead';
  return (
    <ConfirmDialog
      open={open}
      title={context ? `Replace ${roleLabel} of ${context.teamName}?` : 'Replace role holder?'}
      message={
        context
          ? `Team ${context.teamName} already has a ${roleLabel} ` +
            `(${context.sittingHolder.name}). Do you want to replace them ` +
            `with ${context.newHolderName}? They will be demoted to a regular Member.`
          : ''
      }
      confirmLabel={context ? `Replace ${roleLabel}` : 'Replace'}
      cancelLabel="Cancel"
      pending={pending}
      onConfirm={onConfirm}
      onCancel={onCancel}
      tone="neutral"
    />
  );
}

/** Pure helper — the at-most-one member already holding ``role`` on
 *  ``teamId``, excluding ``excludeMemberId`` (which is the target of the
 *  new assignment). Returns null when the slot is empty or only the
 *  target sits on it. Callers feed this into the modal's context. */
export function findSittingRoleHolder(
  members: Member[],
  teamId: string,
  role: TeamRole,
  excludeMemberId: string,
): Member | null {
  if (role !== 'MANAGER' && role !== 'LEAD') return null;
  return (
    members.find((m) => m.team_id === teamId && m.team_role === role && m.id !== excludeMemberId) ??
    null
  );
}
