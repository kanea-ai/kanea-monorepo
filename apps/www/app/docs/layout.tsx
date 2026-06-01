import type { Metadata } from 'next';
import { Header } from '@/components/site/Header';
import { DocsSidebar } from '@/components/docs/DocsSidebar';
import { TableOfContents } from '@/components/docs/TableOfContents';
import { docsNav } from '@/lib/docs/nav';

export const metadata: Metadata = {
  title: {
    template: '%s · Kanea Docs',
    default: 'Kanea Docs',
  },
  description:
    'Developer documentation for the Kanea platform: concepts, agent integration, and the full API reference.',
  openGraph: {
    title: 'Kanea Docs',
    description:
      'Developer documentation for the Kanea platform: concepts, agent integration, and the full API reference.',
    type: 'website',
    siteName: 'Kanea',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Kanea Docs',
    description: 'Developer documentation for the Kanea platform.',
  },
  robots: { index: true, follow: true },
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <Header wordmarkHref="/" section="Docs" />

      <div className="mx-auto flex w-full max-w-7xl flex-1 gap-10 px-6 py-10 sm:px-10">
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="sticky top-10">
            <DocsSidebar sections={docsNav} />
          </div>
        </aside>

        <article
          id="doc-content"
          className="min-w-0 flex-1 text-[0.95rem] leading-relaxed text-slate-700"
        >
          {children}
        </article>

        <aside className="hidden w-56 shrink-0 xl:block">
          <div className="sticky top-10">
            <TableOfContents />
          </div>
        </aside>
      </div>

      <footer className="border-t border-slate-200 px-6 py-6 text-center text-xs text-slate-500 sm:px-10">
        © {new Date().getFullYear()} Kanea
      </footer>
    </div>
  );
}
