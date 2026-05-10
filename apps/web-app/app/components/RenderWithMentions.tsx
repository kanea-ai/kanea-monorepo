'use client';

// Pure-presentation: renders a body string with @handles styled inline.
// Mirrors the regex the api uses for extraction so what the user sees
// is exactly what the api will treat as a mention. No editing — that
// goes through MentionTextarea on input.

import { Fragment } from 'react';

const RE = /(?<=^|[\s,(\[])@([a-zA-Z0-9._+\-]+)/g;

export function RenderWithMentions({
  body,
  className,
}: {
  body: string | null | undefined;
  className?: string;
}) {
  if (!body) return null;

  // Walk the regex matches, splicing styled spans in between literal
  // text chunks. Doing it manually (instead of dangerouslySetInnerHTML)
  // keeps us safe from XSS in user-typed bodies.
  const out: React.ReactNode[] = [];
  let cursor = 0;
  for (const m of body.matchAll(RE)) {
    const start = m.index ?? 0;
    if (start > cursor) out.push(body.slice(cursor, start));
    out.push(
      <span key={`m-${start}`} className="rounded bg-indigo-50 px-1 text-indigo-700">
        @{m[1]}
      </span>,
    );
    cursor = start + m[0].length;
  }
  if (cursor < body.length) out.push(body.slice(cursor));

  return (
    <p className={className ?? 'whitespace-pre-wrap break-words text-sm text-slate-800'}>
      {out.map((node, i) => (
        <Fragment key={i}>{node}</Fragment>
      ))}
    </p>
  );
}
