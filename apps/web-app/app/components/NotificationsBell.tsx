'use client';

// Bell icon + dropdown panel listing recent notifications. The bell
// lives in the AppShell header next to "Sign out". Click → opens a
// floating panel anchored to the bell. The unread count auto-refreshes
// every 30s so the badge stays close to live.

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadCount,
} from '../lib/queries';
import type { NotificationItem } from '../lib/api';

/** Where the dropdown panel anchors relative to the bell.
 *  - 'right' (default): the panel's right edge aligns with the bell —
 *    use when the bell sits near the RIGHT edge of the viewport (mobile
 *    top bar). The 22rem panel extends leftward.
 *  - 'left': the panel's left edge aligns with the bell — use when the
 *    bell sits in a LEFT-side surface (desktop sidebar) where the
 *    default 'right' anchor would overflow the left of the screen.
 *  The component does not pick this dynamically because the bell's
 *  surrounding layout dictates which side has space; callers pass the
 *  right one for their context. */
type Alignment = 'left' | 'right';

interface NotificationsBellProps {
  align?: Alignment;
}

export function NotificationsBell({ align = 'right' }: NotificationsBellProps = {}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { data: count } = useUnreadCount();
  const { data: items, isLoading } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const unread = count?.unread ?? 0;

  // Click outside closes.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ''}`}
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-md p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
      >
        <BellIcon />
        {unread > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          className={`absolute z-40 mt-2 w-[22rem] max-w-[calc(100vw-1rem)] rounded-lg border border-slate-200 bg-white shadow-xl ${
            align === 'left' ? 'left-0' : 'right-0'
          }`}
        >
          <header className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold text-slate-900">Notifications</span>
            <button
              type="button"
              onClick={() => markAll.mutate()}
              disabled={!unread || markAll.isPending}
              className="text-[11px] font-medium text-indigo-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
            >
              Mark all read
            </button>
          </header>

          <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
            {isLoading ? (
              <li className="px-4 py-6 text-center text-sm text-slate-500">Loading…</li>
            ) : !items || items.length === 0 ? (
              <li className="px-4 py-6 text-center text-sm italic text-slate-500">
                No notifications yet. You&apos;ll see @mentions here.
              </li>
            ) : (
              items.map((n) => (
                <Row
                  key={n.id}
                  item={n}
                  onOpen={() => {
                    if (!n.read_at) markRead.mutate(n.id);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Row({ item, onOpen }: { item: NotificationItem; onOpen: () => void }) {
  const verb = item.type === 'MENTION_COMMENT' ? 'commented' : 'mentioned you';
  const actor = item.source_member_name ?? 'Someone';
  const target = item.source_task_id ? `/tasks/${item.source_task_id}` : '#';

  return (
    <li className={item.read_at ? 'bg-white' : 'bg-indigo-50/50'}>
      <Link href={target} onClick={onOpen} className="block px-4 py-3 hover:bg-slate-50">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-slate-800">
            <span className="font-medium">{actor}</span>{' '}
            <span className="text-slate-500">{verb}</span>
          </p>
          {!item.read_at ? (
            <span
              aria-label="Unread"
              className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-indigo-600"
            />
          ) : null}
        </div>
        {item.preview ? (
          <p className="mt-1 line-clamp-2 text-xs text-slate-500">{item.preview}</p>
        ) : null}
        <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-400">
          {formatRelative(item.created_at)}
        </p>
      </Link>
    </li>
  );
}

function BellIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

function formatRelative(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diff = Date.now() - ts;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
