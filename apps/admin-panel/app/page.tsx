'use client';

import { AdminShell } from './components/AdminShell';
import { useRequireAuth } from './lib/auth';

export default function DashboardPage() {
  const ready = useRequireAuth();
  if (!ready) return null;

  return (
    <AdminShell>
      <div className="space-y-6 p-6">
        <header>
          <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
          <p className="text-sm text-slate-500">
            Platform metrics land here in the next task. For now, head to{' '}
            <span className="font-mono">Workspaces</span> to manage tenants.
          </p>
        </header>
        <section className="rounded-lg border border-dashed border-slate-200 bg-white p-6 text-sm italic text-slate-500">
          Workspace counts / user counts / token totals are wired up in Task 4.
        </section>
      </div>
    </AdminShell>
  );
}
