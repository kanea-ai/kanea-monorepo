'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { NavSection } from '@/lib/docs/nav';

interface DocsSidebarProps {
  sections: NavSection[];
}

export function DocsSidebar({ sections }: DocsSidebarProps) {
  const pathname = usePathname();
  return (
    <nav aria-label="Docs navigation" className="flex flex-col gap-6 text-sm">
      {sections.map((section) => (
        <div key={section.title} className="flex flex-col gap-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {section.title}
          </div>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? 'page' : undefined}
                    className={
                      isActive
                        ? 'block rounded-md bg-indigo-50 px-3 py-1.5 font-medium text-indigo-700'
                        : 'block rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }
                  >
                    {item.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
