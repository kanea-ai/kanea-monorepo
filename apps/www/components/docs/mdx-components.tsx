import type { MDXComponents } from 'mdx/types';
import type { AnchorHTMLAttributes, HTMLAttributes } from 'react';
import Link from 'next/link';

import { Callout } from './Callout';
import { CodeBlock } from './CodeBlock';
import { EndpointCard } from './EndpointCard';
import { MethodBadge } from './MethodBadge';

// Maps MDX-rendered elements onto our brand-styled primitives. Heading
// IDs come from rehype-slug (configured in next.config.mjs), so links
// to "#some-section" land correctly.

function H1({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h1
      {...props}
      className={`mb-2 mt-0 text-3xl font-semibold tracking-tight text-slate-900 ${className ?? ''}`}
    />
  );
}

function H2({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      {...props}
      className={`mb-3 mt-10 scroll-mt-24 text-2xl font-semibold tracking-tight text-slate-900 ${className ?? ''}`}
    />
  );
}

function H3({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      {...props}
      className={`mb-2 mt-8 scroll-mt-24 text-xl font-semibold tracking-tight text-slate-900 ${className ?? ''}`}
    />
  );
}

function P({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p {...props} className={`my-4 leading-relaxed text-slate-700 ${className ?? ''}`} />;
}

function A({ href, className, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const isInternal = href?.startsWith('/');
  if (isInternal && href) {
    return (
      <Link
        href={href}
        {...props}
        className={`text-indigo-700 underline-offset-2 hover:underline ${className ?? ''}`}
      />
    );
  }
  return (
    <a
      href={href}
      {...props}
      className={`text-indigo-700 underline-offset-2 hover:underline ${className ?? ''}`}
    />
  );
}

function UL({ className, ...props }: HTMLAttributes<HTMLUListElement>) {
  return (
    <ul {...props} className={`my-4 list-disc space-y-1 pl-6 text-slate-700 ${className ?? ''}`} />
  );
}

function OL({ className, ...props }: HTMLAttributes<HTMLOListElement>) {
  return (
    <ol
      {...props}
      className={`my-4 list-decimal space-y-1 pl-6 text-slate-700 ${className ?? ''}`}
    />
  );
}

function InlineCode({ className, ...props }: HTMLAttributes<HTMLElement>) {
  // rehype-pretty-code marks block-level <code> with data-language. For
  // inline <code> we want a subtle pill; block-level passes through
  // (the parent <pre> handles styling).
  if ((props as { 'data-language'?: string })['data-language']) {
    return <code {...props} className={className} />;
  }
  return (
    <code
      {...props}
      className={`rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] text-slate-800 ${className ?? ''}`}
    />
  );
}

function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="my-5 overflow-x-auto rounded-md border border-slate-200">
      <table {...props} className={`w-full border-collapse text-left text-sm ${className ?? ''}`} />
    </div>
  );
}

function TH({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      {...props}
      className={`border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-600 ${className ?? ''}`}
    />
  );
}

function TD({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      {...props}
      className={`border-b border-slate-100 px-3 py-2 align-top text-slate-700 last:border-b-0 ${className ?? ''}`}
    />
  );
}

function Hr(props: HTMLAttributes<HTMLHRElement>) {
  return <hr {...props} className="my-8 border-t border-slate-200" />;
}

export const mdxComponents: MDXComponents = {
  h1: H1,
  h2: H2,
  h3: H3,
  p: P,
  a: A,
  ul: UL,
  ol: OL,
  code: InlineCode,
  pre: CodeBlock,
  table: Table,
  th: TH,
  td: TD,
  hr: Hr,
  Callout,
  EndpointCard,
  MethodBadge,
};
