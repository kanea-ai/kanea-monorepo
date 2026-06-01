import type { ReactNode } from 'react';

type Variant = 'info' | 'warning' | 'note';

interface CalloutProps {
  variant?: Variant;
  title?: string;
  children: ReactNode;
}

const styles: Record<Variant, { wrapper: string; title: string }> = {
  info: {
    wrapper: 'border-indigo-200 bg-indigo-50/60 text-indigo-900',
    title: 'text-indigo-900',
  },
  warning: {
    wrapper: 'border-amber-200 bg-amber-50/60 text-amber-900',
    title: 'text-amber-900',
  },
  note: {
    wrapper: 'border-slate-200 bg-slate-50 text-slate-700',
    title: 'text-slate-900',
  },
};

export function Callout({ variant = 'info', title, children }: CalloutProps) {
  const s = styles[variant];
  return (
    <aside
      data-variant={variant}
      role="note"
      className={`my-5 rounded-md border px-4 py-3 text-sm ${s.wrapper}`}
    >
      {title ? <div className={`mb-1 font-semibold ${s.title}`}>{title}</div> : null}
      <div className="leading-relaxed [&>p+p]:mt-2 [&>p]:m-0">{children}</div>
    </aside>
  );
}
