'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, type ReactNode } from 'react';

import { useAuth, useRequireAuth } from '../lib/auth';
import { useBlockedTasks } from '../lib/queries';

interface NavItem {
  href: string;
  label: string;
  /** Optional badge value, e.g. blocked count. */
  badge?: number;
}

export function AppShell({ children }: { children: ReactNode }) {
  const ready = useRequireAuth();
  const pathname = usePathname();
  const { logout } = useAuth();
  const [navOpen, setNavOpen] = useState(false);

  // Pull the blocked count for the sidebar badge. Cached + auto-refreshed by
  // useBlockedTasks; safe to share across pages.
  const { data: blocked } = useBlockedTasks();

  const items: NavItem[] = [
    { href: '/', label: 'Dashboard' },
    { href: '/board', label: 'Board' },
    { href: '/projects', label: 'Projects' },
    { href: '/blocked', label: 'Blocked', badge: blocked?.length },
    { href: '/teams', label: 'Teams' },
    { href: '/members', label: 'Members' },
    { href: '/agents', label: 'Agents' },
    { href: '/profile', label: 'My profile' },
  ];

  // Until the auth state has been read from storage we render nothing — the
  // useRequireAuth hook will redirect to /login if there's no token.
  if (!ready) return null;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 lg:flex-row">
      {/* Mobile top bar */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <Link href="/" className="text-sm font-semibold tracking-tight text-slate-900">
          Kanea
        </Link>
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
      </header>

      {/* Sidebar — fixed on desktop, collapsible drawer on mobile */}
      <aside
        className={`${navOpen ? 'block' : 'hidden'} border-b border-slate-200 bg-white lg:flex lg:w-56 lg:shrink-0 lg:flex-col lg:border-b-0 lg:border-r`}
      >
        <div className="hidden px-5 py-4 lg:block">
          <Link href="/" className="text-sm font-semibold tracking-tight text-slate-900">
            Kanea
          </Link>
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
        <div className="mt-auto hidden border-t border-slate-200 p-3 lg:block">
          <button
            type="button"
            onClick={logout}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            Sign out
          </button>
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
