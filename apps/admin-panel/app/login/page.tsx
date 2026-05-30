'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';

export default function LoginPage() {
  const { login, token, isReady } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already signed in → bounce to dashboard so the login form isn't a
  // dead-end the user has to logout from to escape.
  useEffect(() => {
    if (isReady && token) router.replace('/');
  }, [isReady, token, router]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email.trim(), password);
      router.replace('/');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Login failed');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-700">Kanea</p>
          <h1 className="text-xl font-semibold text-slate-900">Back-office sign in</h1>
          <p className="mt-1 text-xs text-slate-500">
            Restricted to platform superadmins. Your{' '}
            <span className="font-mono">users.is_superadmin</span> flag must be set via{' '}
            <span className="font-mono">scripts/make_superadmin.py</span> — no UI path elevates.
          </p>
        </div>
        <div>
          <label
            htmlFor="email"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
          />
        </div>
        <div>
          <label
            htmlFor="password"
            className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-600"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
          />
        </div>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-md bg-rose-700 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
