'use client';

// Landing page for the OAuth round-trip. The api's /oauth/{provider}/callback
// handler 302s the browser here with `?token=…` (success) or `?error=…`
// (provider denied / consent failed). We hydrate the AuthContext from the
// token, then bounce to the dashboard.

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

import { TOKEN_STORAGE_KEY } from '../../lib/api';

export default function AuthCallbackPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Suspense fallback={<Spinner />}>
        <CallbackHandler />
      </Suspense>
    </main>
  );
}

function CallbackHandler() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const providerError = params.get('error');
    if (providerError) {
      setError(providerError);
      return;
    }

    const token = params.get('token');
    if (!token) {
      setError('missing_token');
      return;
    }

    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    router.replace('/');
  }, [params, router]);

  if (error) {
    return (
      <div className="w-full max-w-sm rounded-xl border border-red-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">Sign-in failed</h1>
        <p className="mt-2 text-sm text-slate-600">
          The sign-in flow returned an error: <code className="text-red-600">{error}</code>.
        </p>
        <a
          href="/login"
          className="mt-4 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Try again
        </a>
      </div>
    );
  }

  return <Spinner />;
}

function Spinner() {
  return (
    <div className="flex flex-col items-center gap-3 text-sm text-slate-500">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600" />
      Signing you in…
    </div>
  );
}
