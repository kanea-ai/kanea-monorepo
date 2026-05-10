'use client';

// Generic pagination footer used by the paginated list views: Audit,
// Teams, Departments, Directory, Blocks, Projects. Shape:
//
//     Showing 26–50 of 312          ‹ 1 2 [3] 4 5 6 7 ›
//
// Driven by parent state — the consumer holds the `page` value (1-
// indexed) and reacts in its useQuery hook. Page numbers stay
// stable: we always render the first, last, current, and a small
// window around current; the rest collapses to ``…`` so the bar
// doesn't grow unbounded.

const WINDOW = 1;

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (next: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), pageCount);

  if (pageCount <= 1) {
    return (
      <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        {total} {total === 1 ? 'item' : 'items'}
      </div>
    );
  }

  const start = (safePage - 1) * pageSize + 1;
  const end = Math.min(safePage * pageSize, total);

  // Build the displayed sequence of "page number | …" tokens.
  const tokens: (number | 'gap')[] = [];
  for (let n = 1; n <= pageCount; n++) {
    const inWindow = Math.abs(n - safePage) <= WINDOW;
    const isEdge = n === 1 || n === pageCount;
    if (inWindow || isEdge) {
      tokens.push(n);
    } else if (tokens[tokens.length - 1] !== 'gap') {
      tokens.push('gap');
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500 sm:flex-row sm:items-center sm:justify-between">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <nav className="flex items-center gap-1" aria-label="Pagination">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, safePage - 1))}
          disabled={safePage === 1}
          aria-label="Previous page"
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ‹
        </button>
        {tokens.map((tok, i) =>
          tok === 'gap' ? (
            <span key={`gap-${i}`} className="select-none px-1 text-slate-400" aria-hidden>
              …
            </span>
          ) : (
            <button
              key={tok}
              type="button"
              onClick={() => onChange(tok)}
              aria-current={tok === safePage ? 'page' : undefined}
              className={`rounded px-2 py-0.5 ${
                tok === safePage
                  ? 'bg-indigo-600 font-medium text-white'
                  : 'border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {tok}
            </button>
          ),
        )}
        <button
          type="button"
          onClick={() => onChange(Math.min(pageCount, safePage + 1))}
          disabled={safePage === pageCount}
          aria-label="Next page"
          className="rounded border border-slate-200 px-2 py-0.5 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          ›
        </button>
      </nav>
    </div>
  );
}
