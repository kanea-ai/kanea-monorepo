import Link from 'next/link';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.kanea.ai';

interface HeaderProps {
  // When set, the wordmark becomes a link to this href and a "· {section}"
  // suffix renders inline. Used on the /docs subarea so the user can
  // navigate back to landing and sees which section they're in. The
  // landing renders neither — passes no props.
  wordmarkHref?: string;
  section?: string;
}

export function Header({ wordmarkHref, section }: HeaderProps) {
  const wordmark = (
    <span className="text-base font-semibold tracking-tight text-slate-900">Kanea</span>
  );

  // When no extras, render the wordmark span as a direct child so the
  // landing markup is byte-identical to its pre-extraction state.
  const left =
    wordmarkHref || section ? (
      <div className="flex items-baseline gap-2">
        {wordmarkHref ? (
          <Link href={wordmarkHref} className="hover:opacity-80">
            {wordmark}
          </Link>
        ) : (
          wordmark
        )}
        {section ? (
          <>
            <span className="text-base font-normal text-slate-400" aria-hidden="true">
              ·
            </span>
            <span className="text-base font-medium tracking-tight text-slate-600">{section}</span>
          </>
        ) : null}
      </div>
    ) : (
      wordmark
    );

  return (
    <header className="flex items-center justify-between border-b border-slate-200/70 bg-white/70 px-6 py-4 backdrop-blur sm:px-10">
      {left}
      <nav className="flex items-center gap-3 text-sm">
        <a
          href={`${APP_URL}/login`}
          className="rounded-md px-3 py-1.5 font-medium text-slate-700 hover:text-slate-900"
        >
          Log in
        </a>
        <a
          href={`${APP_URL}/signup`}
          className="rounded-md bg-indigo-600 px-3 py-1.5 font-medium text-white shadow-sm hover:bg-indigo-700"
        >
          Sign up
        </a>
      </nav>
    </header>
  );
}
