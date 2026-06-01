import Link from 'next/link';
import { Header } from '@/components/site/Header';
import { DocsSidebar } from '@/components/docs/DocsSidebar';
import { docsNav } from '@/lib/docs/nav';

export default function DocsNotFound() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <Header wordmarkHref="/" section="Docs" />

      <div className="mx-auto flex w-full max-w-7xl flex-1 gap-10 px-6 py-10 sm:px-10">
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="sticky top-10">
            <DocsSidebar sections={docsNav} />
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <h1 className="mb-2 mt-0 text-3xl font-semibold tracking-tight text-slate-900">
            Page not found
          </h1>
          <p className="my-4 leading-relaxed text-slate-700">
            The documentation page you were looking for doesn&apos;t exist. The navigation on the
            left lists everything that&apos;s published — start from the{' '}
            <Link href="/docs" className="text-indigo-700 underline-offset-2 hover:underline">
              documentation hub
            </Link>
            , or jump straight into{' '}
            <Link
              href="/docs/getting-started"
              className="text-indigo-700 underline-offset-2 hover:underline"
            >
              Getting started
            </Link>
            .
          </p>
        </main>
      </div>

      <footer className="border-t border-slate-200 px-6 py-6 text-center text-xs text-slate-500 sm:px-10">
        © {new Date().getFullYear()} Kanea
      </footer>
    </div>
  );
}
