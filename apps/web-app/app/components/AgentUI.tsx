'use client';

import type { ReactNode } from 'react';

import type { HealthStatus } from '../lib/api';

// Shared building blocks for the /agents pages. Lives here so the list
// and detail views render identically and so a future plug-in (e.g.
// the projects view) can drop them in.

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  // CSS-only hover tooltip. The native `title` attribute had a 1-2s
  // delay (UA-dependent) and on small icons it sometimes never showed
  // at all — users reported the hint never appeared. group-hover gives
  // us instant, deterministic display.
  return (
    <span className="group relative inline-flex items-center">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-1/2 top-full z-20 mt-1.5 w-max max-w-[14rem] -translate-x-1/2 rounded bg-slate-900 px-2 py-1 text-[11px] font-normal normal-case leading-snug tracking-normal text-white opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100"
      >
        {content}
      </span>
    </span>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}) {
  // Hint is rendered as a hover tooltip next to the label rather than a
  // paragraph below the input, so every field in a grid stays the same
  // height regardless of which fields carry hints.
  return (
    <div>
      <div className="mb-1 flex items-center gap-1">
        <label
          htmlFor={htmlFor}
          className="block text-xs font-medium uppercase tracking-wide text-slate-600"
        >
          {label}
        </label>
        {hint ? (
          <Tooltip content={hint}>
            <span
              aria-label={hint}
              className="inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-slate-300 text-[9px] font-semibold text-slate-500"
            >
              ?
            </span>
          </Tooltip>
        ) : null}
      </div>
      {children}
    </div>
  );
}

export function HealthPill({
  status,
  lastSeenAt,
  size = 'md',
}: {
  status: HealthStatus;
  lastSeenAt: string | null;
  size?: 'sm' | 'md';
}) {
  const tone =
    status === 'ONLINE'
      ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
      : status === 'IDLE'
        ? 'border-amber-300 bg-amber-50 text-amber-800'
        : 'border-slate-300 bg-slate-100 text-slate-600';
  const dot =
    status === 'ONLINE' ? 'bg-emerald-500' : status === 'IDLE' ? 'bg-amber-500' : 'bg-slate-400';
  const sizing =
    size === 'sm' ? 'px-1.5 py-0.5 text-[9px] gap-1' : 'px-2 py-0.5 text-[10px] gap-1.5';
  const tooltip = lastSeenAt
    ? `Last seen ${formatRelative(lastSeenAt)} (${new Date(lastSeenAt).toLocaleString()})`
    : 'Never seen — agent has not authenticated yet.';
  return (
    <Tooltip content={tooltip}>
      <span
        className={`inline-flex items-center rounded-full border font-semibold uppercase tracking-wide ${tone} ${sizing}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        {status}
      </span>
    </Tooltip>
  );
}

export function formatRelative(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}
