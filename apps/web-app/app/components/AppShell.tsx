'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';

import { useAuth, useRequireAuth } from '../lib/auth';
import { useBlockedTasks, useMe } from '../lib/queries';
import { NotificationsBell } from './NotificationsBell';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';

// Tiny placeholder while auth state hydrates. Without this the page
// is literally blank until localStorage has been read AND any redirect
// to /login has fired — which can be visible (~1 frame in prod, longer
// the first time chunks compile in dev). Showing "something" makes the
// app feel alive even on the slowest first paint.
function AuthGate({ children }: { children: ReactNode }) {
  const { isReady, token } = useAuth();
  if (!isReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
          Loading Kanea…
        </div>
      </div>
    );
  }
  if (!token) {
    // useRequireAuth's effect has already kicked off the redirect to
    // /login. This is the in-between frame — don't render the shell
    // (we'd flash an empty board), just show the same spinner.
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
          Redirecting to sign-in…
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

interface NavItem {
  href: string;
  label: string;
  /** Optional badge value, e.g. blocked count. */
  badge?: number;
}

export function AppShell({ children }: { children: ReactNode }) {
  // Trigger the redirect side-effect for unauthenticated users. The
  // visible placeholder is rendered by AuthGate below.
  useRequireAuth();
  return (
    <AuthGate>
      <AppShellInner>{children}</AppShellInner>
    </AuthGate>
  );
}

function AppShellInner({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  // Pull the blocked count for the sidebar badge. Cached + auto-refreshed by
  // useBlockedTasks; safe to share across pages.
  const { data: blocked } = useBlockedTasks();
  // Drives the bottom-bar Profile button label.
  const { data: me } = useMe();

  // Order matters: Dashboard → Board → Projects → Blocks → Directory →
  // Teams → Departments → Audit. Profile sits in the bottom section
  // (see below) — it's the only navigation item not in this list.
  const items: NavItem[] = [
    { href: '/', label: 'Dashboard' },
    { href: '/board', label: 'Board' },
    { href: '/projects', label: 'Projects' },
    { href: '/blocks', label: 'Blocks', badge: blocked?.length },
    { href: '/directory', label: 'Directory' },
    { href: '/teams', label: 'Teams' },
    { href: '/departments', label: 'Departments' },
    // Audit is admin-only at the api level; the link is shown to
    // everyone but unauthorised users get an empty list (USER role)
    // or 403 (priority too low). We render the link unconditionally
    // so admins discover it without us needing to thread the role
    // bit through this component too.
    { href: '/audit', label: 'Audit' },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 lg:flex-row">
      {/* Mobile top bar */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <Link href="/" className="text-sm font-semibold tracking-tight text-slate-900">
          Kanea
        </Link>
        <div className="flex items-center gap-1">
          <NotificationsBell />
          <button
            type="button"
            aria-label="Toggle navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen((v) => !v)}
            className="rounded-md border border-slate-200 px-2 py-1 text-slate-700 hover:bg-slate-50"
          >
            <span className="block h-0.5 w-5 bg-current" />
            <span className="mt-1 block h-0.5 w-5 bg-current" />
            <span className="mt-1 block h-0.5 w-5 bg-current" />
          </button>
        </div>
      </header>

      {/* Sidebar — fixed on desktop, collapsible drawer on mobile */}
      <aside
        className={`${navOpen ? 'block' : 'hidden'} border-b border-slate-200 bg-white lg:flex lg:w-56 lg:shrink-0 lg:flex-col lg:border-b-0 lg:border-r`}
      >
        <div className="hidden items-center justify-between px-5 py-4 lg:flex">
          <Link href="/" className="text-sm font-semibold tracking-tight text-slate-900">
            Kanea
          </Link>
          <NotificationsBell />
        </div>
        <div className="px-3 pb-3 lg:px-3">
          <WorkspaceSwitcher />
        </div>
        <nav className="flex flex-col gap-0.5 px-2 py-2 lg:px-3">
          {items.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              isActive={isActive(pathname, item.href)}
              onNavigate={() => setNavOpen(false)}
            />
          ))}
        </nav>
        {/* Bottom-bar Profile button. Replaces the old Sign-out button —
            sign-out itself moved to the /profile page. The button reads
            as "Profile" with the user's name underneath, so the user
            knows whose profile they're about to open. */}
        <div className="mt-auto hidden border-t border-slate-200 p-2 lg:block">
          <Link
            href="/profile"
            onClick={() => setNavOpen(false)}
            className={`flex w-full flex-col rounded-md px-3 py-2 text-left text-sm transition-colors ${
              isActive(pathname, '/profile')
                ? 'bg-indigo-50 text-indigo-700'
                : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <span className="font-medium">Profile</span>
            {me ? <span className="truncate text-xs text-slate-500">{me.full_name}</span> : null}
          </Link>
        </div>
      </aside>

      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}

function NavLink({
  item,
  isActive,
  onNavigate,
}: {
  item: NavItem;
  isActive: boolean;
  onNavigate: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={`flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors ${
        isActive
          ? 'bg-indigo-50 font-medium text-indigo-700'
          : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900'
      }`}
    >
      <span>{item.label}</span>
      {item.badge && item.badge > 0 ? (
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
            isActive ? 'bg-indigo-100 text-indigo-800' : 'bg-amber-100 text-amber-800'
          }`}
        >
          {item.badge}
        </span>
      ) : null}
    </Link>
  );
}

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}
