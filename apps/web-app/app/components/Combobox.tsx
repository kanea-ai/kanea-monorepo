'use client';

// Searchable combobox / typeahead for the board filters and beyond.
//
// Behaviour:
// - User types in the input → suggestions narrow.
// - Sort: items whose label *starts with* the query rank first; then
//   items that *contain* the query, with each group sorted alphabetically.
// - Limited to 5 visible matches at a time.
// - Selecting an item fills the input and fires onChange(item.value).
// - The "x" button on the right clears the selection (onChange(null)).
//
// State model: `value` is the currently-selected option's id (or null).
// The component owns the search query string only.

import { useEffect, useId, useMemo, useRef, useState } from 'react';

export interface ComboboxOption {
  value: string;
  label: string;
  /** Optional extra hint shown to the right of the label, e.g. "(agent)". */
  hint?: string;
}

interface ComboboxProps {
  options: ComboboxOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  ariaLabel?: string;
  /** Extra classes for the wrapper. The input still gets sensible defaults. */
  className?: string;
  /** Defaults to 5 — the spec for the board filters. */
  maxResults?: number;
  /** Disabled state for the entire control. */
  disabled?: boolean;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = 'Search…',
  ariaLabel,
  className = '',
  maxResults = 5,
  disabled = false,
}: ComboboxProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // The current text in the input. When the user has a selection
  // and isn't typing, this mirrors the selected option's label so the
  // input "looks" like a single-select. While typing, the search
  // string detaches and the dropdown opens.
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const selected = useMemo(
    () => (value == null ? null : (options.find((o) => o.value === value) ?? null)),
    [options, value],
  );

  // Reflect external selection changes back into the visible text when
  // the dropdown is closed. While the user is actively typing we don't
  // overwrite their query.
  useEffect(() => {
    if (!open) setQuery(selected?.label ?? '');
  }, [selected, open]);

  // Filter + rank options. Empty query shows all (still capped to
  // maxResults) — nice when the user clicks the input cold.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ranked = options
      .map((opt) => {
        if (!q) return { opt, score: 2 };
        const lower = opt.label.toLowerCase();
        if (lower.startsWith(q)) return { opt, score: 0 };
        if (lower.includes(q)) return { opt, score: 1 };
        return null;
      })
      .filter((x): x is { opt: ComboboxOption; score: number } => x !== null)
      .sort((a, b) => {
        if (a.score !== b.score) return a.score - b.score;
        return a.opt.label.localeCompare(b.opt.label);
      })
      .slice(0, maxResults)
      .map((x) => x.opt);
    return ranked;
  }, [options, query, maxResults]);

  // Keep the highlighted index inside bounds when the list changes.
  useEffect(() => {
    setHighlight((prev) => (prev >= matches.length ? 0 : prev));
  }, [matches.length]);

  // Click-outside closes the dropdown without changing selection.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery(selected?.label ?? '');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, selected]);

  const choose = (opt: ComboboxOption) => {
    onChange(opt.value);
    setQuery(opt.label);
    setOpen(false);
  };

  const clear = () => {
    onChange(null);
    setQuery('');
    inputRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setHighlight((h) => Math.min(h + 1, Math.max(matches.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && matches[highlight]) {
        e.preventDefault();
        choose(matches[highlight]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setQuery(selected?.label ?? '');
    }
  };

  return (
    <div ref={wrapperRef} className={`relative ${className}`}>
      <div className="relative">
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-listbox`}
          aria-autocomplete="list"
          aria-label={ariaLabel}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          value={query}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className="w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 pr-7 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
        />
        {selected != null ? (
          <button
            type="button"
            aria-label="Clear selection"
            onClick={clear}
            disabled={disabled}
            className="absolute inset-y-0 right-1 my-auto h-5 w-5 rounded text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
          >
            ×
          </button>
        ) : null}
      </div>

      {open && matches.length > 0 ? (
        <ul
          id={`${id}-listbox`}
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {matches.map((opt, i) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              onMouseDown={(e) => {
                // Use mousedown so the click fires before the input's
                // onBlur closes the dropdown (which would null the click).
                e.preventDefault();
                choose(opt);
              }}
              onMouseEnter={() => setHighlight(i)}
              className={`flex cursor-pointer items-center justify-between gap-3 px-3 py-1.5 ${
                i === highlight ? 'bg-indigo-50 text-indigo-900' : 'text-slate-800'
              } ${opt.value === value ? 'font-medium' : ''}`}
            >
              <span className="truncate">{opt.label}</span>
              {opt.hint ? (
                <span className="shrink-0 text-xs text-slate-400">{opt.hint}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
