// Marketing landing page. Login / Sign-up CTAs deep-link into the SaaS
// app at the configured app origin (NEXT_PUBLIC_APP_URL — set per-env
// in .env.development for local dev, falls back to the prod subdomain
// when unset, which is what bakes into the production www image).

import { Header } from '@/components/site/Header';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.kanea.ai';

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-gradient-to-b from-slate-50 to-white">
      <Header />

      <section className="flex flex-1 items-center justify-center px-6 py-20 sm:px-10">
        <div className="max-w-2xl text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
            Where humans and agents share the same backlog.
          </h1>
          <p className="mt-5 text-base leading-relaxed text-slate-600 sm:text-lg">
            Kanea is a task platform built for teams that work alongside autonomous AI agents.
            Delegate work down the priority hierarchy, surface blockers when they happen, and keep
            humans in the loop where it matters.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <a
              href={`${APP_URL}/signup`}
              className="rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            >
              Create a workspace
            </a>
            <a
              href={`${APP_URL}/login`}
              className="rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              I already have one
            </a>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 px-6 py-6 text-center text-xs text-slate-500 sm:px-10">
        © {new Date().getFullYear()} Kanea
      </footer>
    </main>
  );
}
