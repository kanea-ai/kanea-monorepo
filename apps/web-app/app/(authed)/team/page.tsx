'use client';

import { useState, type FormEvent } from 'react';

import { ApiError, type InviteCreateResponse, type Member, type MemberRole } from '../../lib/api';
import { useCreateInvite, useMembers } from '../../lib/queries';

export default function TeamPage() {
  const { data: members, isLoading, isError, error } = useMembers();

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Team</h1>
          <p className="text-sm text-slate-500">
            Invite humans to the workspace and manage who can see what. Agents are managed
            separately on /agents.
          </p>
        </div>
      </header>

      <InviteSection />

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <header className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Members</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Everyone with access to this workspace, including agents.
          </p>
        </header>
        <div className="p-1">
          {isError ? (
            <p className="px-3 py-6 text-sm text-red-600">
              Failed to load members: {(error as Error).message}
            </p>
          ) : isLoading ? (
            <SkeletonRows count={3} />
          ) : !members || members.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-slate-500">No members yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {members.map((m) => (
                <MemberRow key={m.id} member={m} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function InviteSection() {
  const createInvite = useCreateInvite();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'ADMIN' | 'MEMBER'>('MEMBER');
  const [lastInvite, setLastInvite] = useState<InviteCreateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const invite = await createInvite.mutateAsync({ email, role });
      setLastInvite(invite);
      setEmail('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create invite');
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Invite a member</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Generates a one-time link. Copy and share it via your usual channel — we don&apos;t send
          email yet.
        </p>
      </header>

      <form
        className="grid gap-3 px-4 py-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
        onSubmit={onSubmit}
      >
        <Field label="Email" htmlFor="invite_email">
          <input
            id="invite_email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="bob@example.com"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>
        <Field label="Role" htmlFor="invite_role">
          <select
            id="invite_role"
            value={role}
            onChange={(e) => setRole(e.target.value as 'ADMIN' | 'MEMBER')}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="MEMBER">Member</option>
            <option value="ADMIN">Admin</option>
          </select>
        </Field>
        <button
          type="submit"
          disabled={createInvite.isPending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {createInvite.isPending ? 'Creating…' : 'Create invite'}
        </button>
      </form>

      {error ? (
        <p role="alert" className="px-4 pb-4 text-sm text-red-600">
          {error}
        </p>
      ) : null}

      {lastInvite ? <InviteLinkReveal invite={lastInvite} /> : null}
    </section>
  );
}

function InviteLinkReveal({ invite }: { invite: InviteCreateResponse }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    await navigator.clipboard.writeText(invite.accept_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="border-t border-slate-100 bg-emerald-50/50 px-4 py-3">
      <p className="text-xs font-medium text-emerald-900">
        Invite created for {invite.email} ({roleLabel(invite.role)}). Token is shown once — copy it
        now.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 truncate rounded border border-emerald-200 bg-white px-2 py-1.5 font-mono text-xs text-slate-800">
          {invite.accept_url}
        </code>
        <button
          type="button"
          onClick={onCopy}
          className="shrink-0 rounded-md border border-emerald-300 bg-white px-3 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

function MemberRow({ member }: { member: Member }) {
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-slate-900">{member.name}</p>
        {member.email ? (
          <p className="mt-0.5 truncate text-xs text-slate-500">{member.email}</p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {member.type === 'AGENT' ? (
          <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-800">
            Agent
          </span>
        ) : null}
        <RolePill role={member.role} />
      </div>
    </li>
  );
}

const ROLE_PILL: Record<MemberRole, string> = {
  OWNER: 'bg-indigo-100 text-indigo-800',
  ADMIN: 'bg-blue-100 text-blue-800',
  MEMBER: 'bg-slate-100 text-slate-700',
};

function RolePill({ role }: { role: MemberRole }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROLE_PILL[role]}`}
    >
      {roleLabel(role)}
    </span>
  );
}

function roleLabel(role: MemberRole): string {
  return role.charAt(0) + role.slice(1).toLowerCase();
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <ul className="divide-y divide-slate-100">
      {Array.from({ length: count }).map((_, i) => (
        <li key={i} className="px-3 py-3">
          <div className="h-3 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/4 animate-pulse rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
      >
        {label}
      </label>
      {children}
    </div>
  );
}
