'use client';

// Both buttons trigger a full-page navigation to the api's /oauth/{provider}
// /login endpoint, which 302s through the provider and back to /auth/callback
// with the JWT. Using a real <a href> (not fetch) is intentional — OAuth
// flows need top-level navigation so the provider can set its own session
// cookies and redirect.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

export function OAuthButtons({ mode }: { mode: 'login' | 'signup' }) {
  const verb = mode === 'signup' ? 'Sign up' : 'Continue';
  return (
    <div className="space-y-2">
      <a
        href={`${API_BASE}/api/v1/auth/oauth/GOOGLE/login`}
        className="flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50"
      >
        <GoogleMark />
        {verb} with Google
      </a>
      <a
        href={`${API_BASE}/api/v1/auth/oauth/GITHUB/login`}
        className="flex w-full items-center justify-center gap-2 rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-slate-800"
      >
        <GitHubMark />
        {verb} with GitHub
      </a>
    </div>
  );
}

export function Divider({ label = 'or' }: { label?: string }) {
  return (
    <div className="my-4 flex items-center gap-3 text-xs uppercase tracking-wide text-slate-400">
      <span className="h-px flex-1 bg-slate-200" />
      {label}
      <span className="h-px flex-1 bg-slate-200" />
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34 6 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 15.4 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34 6 29.3 4 24 4 16.4 4 9.8 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.5-5.2l-6.2-5.2c-2 1.5-4.5 2.4-7.3 2.4-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.7 39.6 16.3 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.3 5.6l6.2 5.2c-.4.4 6.8-5 6.8-14.8 0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

function GitHubMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M12 .5C5.4.5 0 5.9 0 12.6c0 5.3 3.4 9.8 8.2 11.4.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1.1-.8.1-.8.1-.8 1.2.1 1.9 1.3 1.9 1.3 1.1 1.9 2.9 1.4 3.6 1 .1-.8.4-1.4.8-1.7-2.7-.3-5.5-1.3-5.5-6 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2.9-.3 2-.4 3-.4s2 .1 3 .4c2.3-1.5 3.3-1.2 3.3-1.2.7 1.7.3 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6C20.6 22.4 24 17.9 24 12.6 24 5.9 18.6.5 12 .5z"
      />
    </svg>
  );
}
