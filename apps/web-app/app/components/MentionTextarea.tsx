'use client';

// Textarea + @-mention picker. Phase 4.
//
// When the caret sits inside an @<query> token, a small dropdown of
// matching humans appears under the textarea. Selecting one swaps the
// token for the member's email-local-part (`@alice`) — that's the
// canonical handle the api will resolve back to a user.
//
// Agents are filtered out at the source — the spec says only humans
// can be mentioned. The component takes the workspace member list as
// a prop so the caller doesn't need to fetch from inside.

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';

import type { Member } from '../lib/api';

interface MentionTextareaProps {
  value: string;
  onChange: (value: string) => void;
  members: Member[];
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  className?: string;
  /** When true, hitting Enter in the trigger dropdown picks a match
   * (Enter still inserts a newline outside the dropdown). */
  selectOnEnter?: boolean;
}

interface ActiveTrigger {
  // Position of the @ in the string.
  start: number;
  // Position after the partial query (== caret).
  end: number;
  query: string;
}

const HUMAN_PRIORITY = (m: Member) => m.priority;

function localPart(email: string | null): string | null {
  if (!email) return null;
  const at = email.indexOf('@');
  return at < 0 ? email : email.slice(0, at);
}

function detectTrigger(text: string, caret: number): ActiveTrigger | null {
  // Walk back from the caret looking for an @ at a token boundary.
  // Stop if we hit whitespace/punctuation that breaks the token.
  let i = caret - 1;
  while (i >= 0) {
    const ch = text[i];
    if (ch === '@') {
      // Boundary check: the char before @ must be whitespace, start
      // of string, or one of the safe leading characters.
      if (i === 0 || /[\s,(\[]/.test(text[i - 1])) {
        return { start: i, end: caret, query: text.slice(i + 1, caret) };
      }
      return null;
    }
    if (/\s/.test(ch)) return null;
    i -= 1;
  }
  return null;
}

export function MentionTextarea({
  value,
  onChange,
  members,
  placeholder,
  rows = 3,
  disabled = false,
  className = '',
}: MentionTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [trigger, setTrigger] = useState<ActiveTrigger | null>(null);
  const [highlight, setHighlight] = useState(0);

  // Pre-compute the mentionable handle list once per member-list change.
  // Email-less members (all current AGENTs) drop out automatically.
  const mentionable = useMemo(
    () =>
      members
        .filter((m) => m.type === 'HUMAN' && m.email != null)
        .map((m) => ({
          member: m,
          handle: (localPart(m.email) ?? '').toLowerCase(),
        }))
        .filter((x) => x.handle.length > 0),
    [members],
  );

  const matches = useMemo(() => {
    if (trigger == null) return [];
    const q = trigger.query.toLowerCase();
    const ranked = mentionable
      .map((x) => {
        if (!q) return { ...x, score: 2 };
        if (x.handle.startsWith(q) || x.member.name.toLowerCase().startsWith(q))
          return { ...x, score: 0 };
        if (x.handle.includes(q) || x.member.name.toLowerCase().includes(q))
          return { ...x, score: 1 };
        return null;
      })
      .filter((v): v is { member: Member; handle: string; score: number } => v !== null)
      .sort((a, b) => {
        if (a.score !== b.score) return a.score - b.score;
        return HUMAN_PRIORITY(a.member) - HUMAN_PRIORITY(b.member);
      })
      .slice(0, 5);
    return ranked;
  }, [mentionable, trigger]);

  // Reset the highlight when the candidate list shrinks under it.
  useEffect(() => {
    setHighlight((prev) => (prev >= matches.length ? 0 : prev));
  }, [matches.length]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    const caret = e.target.selectionStart ?? e.target.value.length;
    setTrigger(detectTrigger(e.target.value, caret));
  };

  const choose = (handle: string) => {
    if (trigger == null || ref.current == null) return;
    const before = value.slice(0, trigger.start);
    const after = value.slice(trigger.end);
    // Trailing space so the next typed character starts a fresh word.
    const next = `${before}@${handle} ${after}`;
    onChange(next);
    setTrigger(null);
    // Restore caret to right after the inserted handle + space.
    const caret = before.length + handle.length + 2;
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(caret, caret);
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (trigger == null || matches.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, matches.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(matches[highlight].handle);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setTrigger(null);
    }
  };

  return (
    <div className={`relative ${className}`}>
      <textarea
        ref={ref}
        rows={rows}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={handleChange}
        onKeyDown={onKeyDown}
        onClick={(e) => {
          // Caret moved without a keystroke — re-detect.
          const caret = (e.target as HTMLTextAreaElement).selectionStart ?? value.length;
          setTrigger(detectTrigger(value, caret));
        }}
        onBlur={() => {
          // Slight delay so a click on the dropdown lands before close.
          setTimeout(() => setTrigger(null), 100);
        }}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      />

      {trigger && matches.length > 0 ? (
        <ul
          role="listbox"
          className="absolute left-3 z-30 mt-1 max-h-56 w-72 overflow-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg"
          style={{ top: '100%' }}
        >
          {matches.map((m, i) => (
            <li
              key={m.member.id}
              role="option"
              aria-selected={i === highlight}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(m.handle);
              }}
              onMouseEnter={() => setHighlight(i)}
              className={`flex cursor-pointer items-center justify-between gap-3 px-3 py-1.5 ${
                i === highlight ? 'bg-indigo-50 text-indigo-900' : 'text-slate-800'
              }`}
            >
              <span className="truncate font-medium">{m.member.name}</span>
              <span className="shrink-0 text-xs text-slate-400">@{m.handle}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
