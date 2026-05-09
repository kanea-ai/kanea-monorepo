'use client';

// Anonymous accept flow. Lives outside the (authed) route group so a
// signed-in user opening an invite link doesn't bounce through useRequireAuth.
// The accepted invite returns a fresh JWT for the target workspace, which we
// drop into localStorage — replacing any prior session.

import { useRouter } from 'next/navigation';
import { use, useEffect, useState, type FormEvent } from 'react';

import {
  ApiError,
  TOKEN_STORAGE_KEY,
  tenantsApi,
  type InvitePreview,
  type MemberRole,
} from '../../lib/api';

interface PageProps {
  params: Promise<{ token: string }>;
}

export default function InviteAcceptPage({ params }: PageProps) {
  const { token } = use(params);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <InviteFlow token={token} />
      </div>
    </main>
  );
}

function InviteFlow({ token }: { token: string }) {
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadStatus, setLoadStatus] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    tenantsApi
      .previewInvite(token)
      .then((p) => {
        if (!cancelled) setPreview(p);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setLoadStatus(err.status);
          setLoadError(err.detail);
        } else {
          setLoadError('Failed to load invite');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loadError) {
    return (
      <div>
        <h1 className="text-lg font-semibold text-slate-900">{loadHeader(loadStatus)}</h1>
        <p className="mt-2 text-sm text-slate-600">{loadError}</p>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="flex flex-col items-center gap-3 text-sm text-slate-500">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600" />
        Loading invite…
      </div>
    );
  }

  return <AcceptForm token={token} preview={preview} />;
}

function loadHeader(status: number | null): string {
  if (status === 404) return 'Invite not found';
  if (status === 410) return 'Invite expired';
  if (status === 409) return 'Invite already used';
  return 'Something went wrong';
}

function AcceptForm({ token, preview }: { token: string; preview: InvitePreview }) {
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const tokenResp = await tenantsApi.acceptInvite(token, {
        full_name: fullName,
        password,
      });
      window.localStorage.setItem(TOKEN_STORAGE_KEY, tokenResp.access_token);
      router.replace('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to accept invite');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <header className="mb-5">
        <h1 className="text-xl font-semibold text-slate-900">
          Join <span className="text-indigo-700">{preview.workspace_name}</span>
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          You&apos;ve been invited to <code className="text-slate-700">{preview.email}</code> as{' '}
          <span className="font-medium text-slate-700">{roleLabel(preview.role)}</span>.
        </p>
      </header>

      <form className="space-y-4" onSubmit={onSubmit}>
        <Field label="Full name" htmlFor="full_name">
          <input
            id="full_name"
            type="text"
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>

        <Field label="Password" htmlFor="password" hint="At least 8 characters.">
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </Field>

        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Joining…' : `Join ${preview.workspace_name}`}
        </button>
      </form>
    </>
  );
}

function roleLabel(role: MemberRole): string {
  const tail = role.slice('WORKSPACE_'.length);
  return tail.charAt(0) + tail.slice(1).toLowerCase();
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
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
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
