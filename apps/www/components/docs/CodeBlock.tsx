'use client';

import { useRef, useState, type ComponentPropsWithoutRef } from 'react';

// Client wrapper around the <pre> blocks rehype-pretty-code emits.
// Adds a copy-to-clipboard button anchored to the top-right corner.
// rehype-pretty-code sets data-language and data-theme on the <pre>;
// we forward those onto our element so future syntax-highlight CSS
// can hook in.
export function CodeBlock(props: ComponentPropsWithoutRef<'pre'>) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    const text = preRef.current?.innerText ?? '';
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore — clipboard API may be blocked in some contexts
    }
  };

  return (
    <div className="group relative my-5">
      <pre
        ref={preRef}
        {...props}
        className="overflow-x-auto rounded-md border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-xs leading-relaxed text-slate-800"
      />
      <button
        type="button"
        onClick={onCopy}
        aria-label="Copy code"
        className="absolute right-2 top-2 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600 opacity-0 shadow-sm transition-opacity hover:text-slate-900 focus:opacity-100 group-hover:opacity-100"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}
