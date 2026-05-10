'use client';

// /directory — unified People & Agents view (Phase 5 batch 2).
//
// Replaces the old /members + /agents separation. Single dense table
// of every member in the workspace with a HUMAN/AGENT pill, role,
// team, and email columns. Toggle filter (All / Humans / Agents)
// pre-fills the API's humans_only param + a client-side type filter.
//
// "Add" is a split button: Invite Member or Create Agent — opens the
// matching modal. The invite flow lived on /teams in Phase 2 and was
// migrated here for centralisation.
//
// Clicking a row opens a side panel for member editing (admin) or a
// read-only contact card (others) — same component the old /members
// page used.

import { useMemo, useState } from 'react';

import { CreateAgentDialog } from '../../components/CreateAgentDialog';
import { InviteMemberDialog } from '../../components/InviteMemberDialog';
import { MemberDetailDialog } from '../../components/MemberDetailDialog';
import { Pagination } from '../../components/Pagination';
import { ApiError, type Member, type MemberRole } from '../../lib/api';
import { useCurrentPrincipal } from '../../lib/auth';
import { useMembers, useProjects, useTeams } from '../../lib/queries';

const PAGE_SIZE = 25;

type ScopeToggle = 'ALL' | 'HUMAN' | 'AGENT';
type SortKey = 'PRIORITY_ASC' | 'PRIORITY_DESC' | 'NAME';

const ROLE_OPTIONS: { value: MemberRole | ''; label: string }[] = [
  { value: '', label: 'Any role' },
  { value: 'WORKSPACE_OWNER', label: 'Owner' },
  { value: 'WORKSPACE_ADMIN', label: 'Admin' },
  { value: 'WORKSPACE_USER', label: 'User' },
];

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'PRIORITY_ASC', label: 'Priority (high → low)' },
  { value: 'PRIORITY_DESC', label: 'Priority (low → high)' },
  { value: 'NAME', label: 'Name (A → Z)' },
];

export default function DirectoryPage() {
  const principal = useCurrentPrincipal();
  const isAdmin = principal?.role === 'WORKSPACE_OWNER' || principal?.role === 'WORKSPACE_ADMIN';

  const [scope, setScope] = useState<ScopeToggle>('ALL');
  const [name, setName] = useState('');
  const [role, setRole] = useState<MemberRole | ''>('');
  const [teamId, setTeamId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [sort, setSort] = useState<SortKey>('PRIORITY_ASC');
  const [openMember, setOpenMember] = useState<Member | null>(null);
  const [addOpen, setAddOpen] = useState<'invite' | 'agent' | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [page, setPage] = useState(1);

  // The scope tabs (All / Humans / Agents) filter on the type column
  // client-side — that way a single api response feeds both the
  // tab counts AND the visible rows. Sending humans_only=true to the
  // api would shrink the result set and the AGENT count would drop
  // to 0, which read as a bug. Workspace size makes one extra
  // type check per row free.
  const {
    data: membersPage,
    isLoading,
    isError,
    error,
  } = useMembers({
    name: name || undefined,
    role: role || undefined,
    teamId: teamId || undefined,
    projectId: projectId || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  });
  const members = membersPage?.items ?? [];
  const total = membersPage?.total ?? 0;

  const { data: teamsPage } = useTeams();
  const teams = teamsPage?.items ?? [];
  const { data: projectsPage } = useProjects();
  const projects = projectsPage?.items ?? [];

  const visible = useMemo(() => {
    let rows = members;
    if (scope === 'HUMAN') rows = rows.filter((m) => m.type === 'HUMAN');
    else if (scope === 'AGENT') rows = rows.filter((m) => m.type === 'AGENT');
    const sorted = [...rows];
    sorted.sort((a, b) => {
      if (sort === 'NAME') return a.name.localeCompare(b.name);
      if (sort === 'PRIORITY_DESC') return b.priority - a.priority || a.name.localeCompare(b.name);
      // PRIORITY_ASC = lower numeric value first (= higher rank).
      return a.priority - b.priority || a.name.localeCompare(b.name);
    });
    return sorted;
  }, [members, scope, sort]);

  // Counts come from the loaded page only — server pagination means
  // we don't have the full type breakdown without a second query.
  // Acceptable for now; the totals readout below shows the unfiltered
  // ``total`` from the server.
  const counts = useMemo(() => {
    return {
      ALL: members.length,
      HUMAN: members.filter((m) => m.type === 'HUMAN').length,
      AGENT: members.filter((m) => m.type === 'AGENT').length,
    };
  }, [members]);

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Directory</h1>
          <p className="text-sm text-slate-500">
            People &amp; agents in this workspace. Filter by name, role, team, or project. Click a
            row to view details.
          </p>
        </div>
        {isAdmin ? (
          <AddSplitButton
            open={addMenuOpen}
            onToggle={() => setAddMenuOpen((v) => !v)}
            onClose={() => setAddMenuOpen(false)}
            onPick={(kind) => {
              setAddMenuOpen(false);
              setAddOpen(kind);
            }}
          />
        ) : null}
      </header>

      <ScopeTabs scope={scope} setScope={setScope} counts={counts} />

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-2 border-b border-slate-100 p-3 sm:grid-cols-[1fr_auto_auto_auto_auto]">
          <input
            type="search"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setPage(1);
            }}
            placeholder="Search by name…"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value as MemberRole | '');
              setPage(1);
            }}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {ROLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Any team</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Any project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="Sort"
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 text-left">Name</th>
              <th className="px-4 py-2 text-left">Type</th>
              <th className="px-4 py-2 text-left">Workspace role</th>
              <th className="px-4 py-2 text-left">Team</th>
              <th className="px-4 py-2 text-right">Priority</th>
              <th className="hidden px-4 py-2 text-left lg:table-cell">Email</th>
            </tr>
          </thead>
          <tbody>
            {isError ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm text-red-600">
                  Failed to load directory: {(error as ApiError).detail ?? (error as Error).message}
                </td>
              </tr>
            ) : isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm text-slate-500">
                  Loading…
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm italic text-slate-500">
                  No matches.
                </td>
              </tr>
            ) : (
              visible.map((m) => (
                <Row key={m.id} member={m} teams={teams} onOpen={() => setOpenMember(m)} />
              ))
            )}
          </tbody>
        </table>
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
      </section>

      {openMember ? (
        <MemberDetailDialog
          member={openMember}
          isAdmin={isAdmin}
          isSelf={openMember.id === principal?.member_id}
          onClose={() => setOpenMember(null)}
        />
      ) : null}

      <InviteMemberDialog open={addOpen === 'invite'} onClose={() => setAddOpen(null)} />
      <CreateAgentDialog open={addOpen === 'agent'} onClose={() => setAddOpen(null)} />
    </div>
  );
}

function ScopeTabs({
  scope,
  setScope,
  counts,
}: {
  scope: ScopeToggle;
  setScope: (s: ScopeToggle) => void;
  counts: { ALL: number; HUMAN: number; AGENT: number };
}) {
  return (
    <div className="inline-flex rounded-md border border-slate-200 bg-white p-0.5 shadow-sm">
      {(['ALL', 'HUMAN', 'AGENT'] as const).map((s) => {
        const active = scope === s;
        return (
          <button
            key={s}
            type="button"
            onClick={() => setScope(s)}
            className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-colors ${
              active ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
            }`}
          >
            {s === 'ALL' ? 'All' : s === 'HUMAN' ? 'Humans' : 'Agents'}
            <span
              className={`rounded-full px-1.5 text-[10px] ${
                active ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
              }`}
            >
              {counts[s]}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function AddSplitButton({
  open,
  onToggle,
  onClose,
  onPick,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  onPick: (kind: 'invite' | 'agent') => void;
}) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
      >
        Add
        <span className="text-xs">▾</span>
      </button>
      {open ? (
        <>
          {/* Click-shield closes when clicking outside without a global listener. */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={onClose}
            className="fixed inset-0 z-20 cursor-default"
          />
          <div
            role="menu"
            className="absolute right-0 z-30 mt-1 w-48 rounded-md border border-slate-200 bg-white shadow-lg"
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => onPick('invite')}
              className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
            >
              Invite member
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => onPick('agent')}
              className="block w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
            >
              Create agent
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}

const ROLE_PILL: Record<MemberRole, string> = {
  WORKSPACE_OWNER: 'bg-indigo-100 text-indigo-800',
  WORKSPACE_ADMIN: 'bg-blue-100 text-blue-800',
  WORKSPACE_USER: 'bg-slate-100 text-slate-700',
};

function Row({
  member,
  teams,
  onOpen,
}: {
  member: Member;
  teams: { id: string; name: string }[];
  onOpen: () => void;
}) {
  const teamName = member.team_id ? (teams.find((t) => t.id === member.team_id)?.name ?? '—') : '—';
  // Suspended rows are visually muted across the whole row so admins
  // see at a glance who's locked out — not just by the pill in the
  // name column.
  const rowTone = member.is_suspended
    ? 'cursor-pointer border-t border-slate-100 bg-slate-50 text-slate-400 transition-colors hover:bg-slate-100'
    : 'cursor-pointer border-t border-slate-100 transition-colors hover:bg-slate-50';
  return (
    <tr onClick={onOpen} className={rowTone}>
      <td className="px-4 py-2.5 font-medium">
        <div className="flex items-center gap-2">
          <span className={member.is_suspended ? 'text-slate-500' : 'text-slate-900'}>
            {member.name}
          </span>
          {member.is_suspended ? (
            <span className="shrink-0 rounded-full bg-red-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-red-800">
              Suspended
            </span>
          ) : null}
        </div>
      </td>
      <td className="px-4 py-2.5">
        <TypePill type={member.type} />
      </td>
      <td className="px-4 py-2.5">
        <RolePill role={member.role} />
      </td>
      <td className="px-4 py-2.5">
        <span className={member.is_suspended ? 'text-slate-500' : 'text-slate-700'}>
          {teamName}
        </span>
        {member.team_role ? (
          <span className="ml-1.5 text-[10px] uppercase tracking-wide text-slate-400">
            {member.team_role}
          </span>
        ) : null}
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
          P{member.priority}
        </span>
      </td>
      <td
        className={`hidden px-4 py-2.5 lg:table-cell ${
          member.is_suspended ? 'text-slate-400' : 'text-slate-500'
        }`}
      >
        {member.email ?? '—'}
      </td>
    </tr>
  );
}

function TypePill({ type }: { type: 'HUMAN' | 'AGENT' }) {
  if (type === 'AGENT') {
    return (
      <span className="rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700">
        Agent
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
      Human
    </span>
  );
}

function RolePill({ role }: { role: MemberRole }) {
  const tail = role.slice('WORKSPACE_'.length);
  const label = tail.charAt(0) + tail.slice(1).toLowerCase();
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {label}
    </span>
  );
}
