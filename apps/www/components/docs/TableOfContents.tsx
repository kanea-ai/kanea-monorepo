'use client';

import { useEffect, useState } from 'react';

export interface Heading {
  id: string;
  text: string;
  level: 2 | 3;
}

interface TableOfContentsProps {
  // When provided, the TOC renders this list directly. Useful in tests
  // and for pages with hand-curated TOCs.
  headings?: Heading[];
  // The DOM element to extract h2/h3 headings from. Defaults to the
  // doc-content article. Re-runs on pathname change via the `key` the
  // parent supplies.
  scopeSelector?: string;
}

const DEFAULT_SCOPE = '#doc-content';

function extractHeadings(scope: string): Heading[] {
  const root = document.querySelector(scope);
  if (!root) return [];
  const nodes = Array.from(root.querySelectorAll('h2, h3'));
  return nodes
    .filter((node): node is HTMLElement => node instanceof HTMLElement && Boolean(node.id))
    .map((node) => ({
      id: node.id,
      text: node.textContent ?? '',
      level: node.tagName === 'H3' ? 3 : 2,
    }));
}

export function TableOfContents({ headings, scopeSelector = DEFAULT_SCOPE }: TableOfContentsProps) {
  const [extracted, setExtracted] = useState<Heading[]>(headings ?? []);

  useEffect(() => {
    if (headings) return;
    setExtracted(extractHeadings(scopeSelector));
  }, [headings, scopeSelector]);

  const list = headings ?? extracted;
  if (list.length === 0) return null;

  return (
    <nav aria-label="On this page" className="flex flex-col gap-2 text-sm">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        On this page
      </div>
      <ul className="flex flex-col gap-1">
        {list.map((h) => (
          <li key={h.id} className={h.level === 3 ? 'ml-3' : undefined}>
            <a href={`#${h.id}`} className="block text-slate-600 hover:text-indigo-700">
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
