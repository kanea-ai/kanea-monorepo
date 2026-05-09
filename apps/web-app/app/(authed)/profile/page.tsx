'use client';

// /profile — the logged-in user's self-service page. Phase 2.
//
// Three sections: identity (rename), password (rotate), stats. Stats
// reuse the same compute_agent_stats SQL the agents page uses, so the
// numbers are consistent across the app — assigned excludes DONE/
// CANCELLED, completed counts only DONE.

import { useEffect, useState, type FormEvent } from 'react';

import { ApiError } from '../../lib/api';
import { useChangePassword, useMe, useMeStats, useUpdateMe } from '../../lib/queries';

export default function ProfilePage() {
  const { data: me, isLoading: meLoading, isError: meError, error: meErr } = useMe();
  const { data: stats } = useMeStats();

  if (meLoading) {
    return <p className="p-6 text-sm text-slate-500">Loading profile…</p>;
  }
  if (meError || !me) {
    return (
      <p className="p-6 text-sm text-red-600">
        Failed to load profile: {(meErr as Error)?.message ?? 'unknown'}
      </p>
    );
  }

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">My profile</h1>
        <p className="text-sm text-slate-500">
          You&apos;re signed in as <span className="font-medium">{me.email}</span> in workspace{' '}
          <span className="font-medium">{me.workspace_name}</span>.
        </p>
      </header>

      <IdentitySection
        currentName={me.full_name}
        email={me.email}
        oauthProvider={me.oauth_provider}
      />

      <PasswordSection hasPassword={me.has_password} />

      <StatsSection
        assigned={stats?.assigned_count}
        completed={stats?.completed_count}
        avgResolutionSec={stats?.avg_resolution_seconds ?? null}
        lastActivity={stats?.last_activity_at ?? null}
        tokens={stats?.total_tokens_used}
      />
    </div>
  );
}

function IdentitySection({
  currentName,
  email,
  oauthProvider,
}: {
  currentName: string;
  email: string;
  oauthProvider: string | null;
}) {
  const update = useUpdateMe();
  const [name, setName] = useState(currentName);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Sync local state when the parent's data changes (e.g. after save).
  useEffect(() => setName(currentName), [currentName]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await update.mutateAsync({ full_name: name.trim() });
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save');
    }
  };

  return (
    <Section title="Identity" subtitle="Update the name shown on your profile and tasks.">
      <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={onSubmit}>
        <div>
          <Label htmlFor="me_name">Display name</Label>
          <input
            id="me_name"
            type="text"
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={update.isPending || name.trim() === currentName || name.trim() === ''}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {update.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>

      <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-[8rem_1fr]">
        <dt className="text-slate-500">Email</dt>
        <dd className="text-slate-700">{email}</dd>
        <dt className="text-slate-500">Sign-in</dt>
        <dd className="text-slate-700">
          {oauthProvider ? `OAuth (${oauthProvider})` : 'Email + password'}
        </dd>
      </dl>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      ) : null}
      {saved ? <p className="mt-3 text-sm text-emerald-700">Saved.</p> : null}
    </Section>
  );
}

function PasswordSection({ hasPassword }: { hasPassword: boolean }) {
  const change = useChangePassword();
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    if (newPwd !== confirmPwd) {
      setError('New password and confirmation do not match.');
      return;
    }
    try {
      await change.mutateAsync({
        current_password: currentPwd,
        new_password: newPwd,
      });
      setSaved(true);
      setCurrentPwd('');
      setNewPwd('');
      setConfirmPwd('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to change password');
    }
  };

  if (!hasPassword) {
    return (
      <Section
        title="Password"
        subtitle="You signed in via OAuth. Setting a password from this account is not supported yet — sign in with your provider."
      >
        <p className="text-sm text-slate-500">No action available.</p>
      </Section>
    );
  }

  return (
    <Section title="Password" subtitle="Rotate your sign-in password.">
      <form className="grid gap-3 sm:max-w-md" onSubmit={onSubmit}>
        <div>
          <Label htmlFor="cur_pwd">Current password</Label>
          <input
            id="cur_pwd"
            type="password"
            required
            value={currentPwd}
            autoComplete="current-password"
            onChange={(e) => setCurrentPwd(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <Label htmlFor="new_pwd">New password</Label>
          <input
            id="new_pwd"
            type="password"
            required
            minLength={8}
            value={newPwd}
            autoComplete="new-password"
            onChange={(e) => setNewPwd(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <Label htmlFor="confirm_pwd">Confirm new password</Label>
          <input
            id="confirm_pwd"
            type="password"
            required
            minLength={8}
            value={confirmPwd}
            autoComplete="new-password"
            onChange={(e) => setConfirmPwd(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <button
            type="submit"
            disabled={change.isPending}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {change.isPending ? 'Saving…' : 'Update password'}
          </button>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
        {saved ? <p className="text-sm text-emerald-700">Password updated.</p> : null}
      </form>
    </Section>
  );
}

function StatsSection({
  assigned,
  completed,
  avgResolutionSec,
  lastActivity,
  tokens,
}: {
  assigned?: number;
  completed?: number;
  avgResolutionSec: number | null;
  lastActivity: string | null;
  tokens?: number;
}) {
  return (
    <Section title="Activity" subtitle="Your task throughput in this workspace.">
      <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <Stat label="Open assignments" value={assigned ?? '—'} />
        <Stat label="Tasks completed" value={completed ?? '—'} />
        <Stat
          label="Avg resolution"
          value={avgResolutionSec != null ? formatDuration(avgResolutionSec) : '—'}
        />
        <Stat
          label="Last activity"
          value={lastActivity ? new Date(lastActivity).toLocaleString() : '—'}
        />
        <Stat label="Tokens used" value={tokens ?? '—'} />
      </dl>
    </Section>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-slate-100 pb-1.5 last:border-b-0">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium tabular-nums text-slate-900">{value}</dd>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
    >
      {children}
    </label>
  );
}
