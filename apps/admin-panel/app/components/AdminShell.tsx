'use client';

// Authenticated shell: left rail with the back-office sections + a
// top bar that surfaces the logged-in superadmin's email + a logout
// button. Every authed page wraps its body with this component.

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { useAdminHealth } from '../lib/queries';
import { useAuth } from '../lib/auth';

const NAV: { href: '/' | '/workspaces'; label: string }[] = [
  { href: '/', label: 'Dashboard' },
  { href: '/workspaces', label: 'Workspaces' },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();
  const { data: health, isError } = useAdminHealth();

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-700">Kanea</p>
          <p className="text-sm font-semibold text-slate-900">Back-office</p>
        </div>
        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-md px-3 py-1.5 text-sm transition ${
                  active
                    ? 'bg-rose-50 font-semibold text-rose-800'
                    : 'text-slate-700 hover:bg-slate-50'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-200 px-4 py-3 text-[11px] text-slate-500">
          <p className="font-medium text-slate-700">{health?.email ?? '—'}</p>
          <p className={isError ? 'text-red-600' : 'text-emerald-700'}>
            {isError ? 'Gate denied' : 'Superadmin ✓'}
          </p>
          <button
            type="button"
            onClick={() => {
              logout();
              router.replace('/login');
            }}
            className="mt-2 w-full rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
