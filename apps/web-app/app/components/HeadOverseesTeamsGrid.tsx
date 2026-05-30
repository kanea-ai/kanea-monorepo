'use client';

// Grid of clickable team cards rendered on a Department Head's
// profile (both /profile for the logged-in user and
// MemberDetailDialog for admins inspecting someone else). Each card
// links into the team's detail page via ``teamHref``.
//
// Used in head-only branches; the non-head case is handled by the
// callers and never reaches this component. The empty state still
// renders so a department with no teams yet reads as intentional
// rather than missing data.

import Link from 'next/link';

import type { TeamRecord } from '../lib/api';
import { teamHref } from '../lib/links';

export function HeadOverseesTeamsGrid({ teams }: { teams: TeamRecord[] }) {
  if (teams.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-center text-xs italic text-slate-500">
        No teams filed under this department yet.
      </p>
    );
  }
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {teams.map((t) => (
        <li key={t.id}>
          <Link
            href={teamHref(t.id)}
            className="group flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-slate-900">{t.name}</p>
              {t.description ? (
                <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">{t.description}</p>
              ) : null}
            </div>
            <span className="text-slate-400 transition group-hover:text-indigo-600">›</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
