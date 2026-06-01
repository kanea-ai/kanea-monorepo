import type { MetadataRoute } from 'next';
import { docsNav } from '@/lib/docs/nav';

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://kanea.ai';

export default function sitemap(): MetadataRoute.Sitemap {
  const docsPaths = new Set<string>(['/docs']);
  for (const section of docsNav) {
    for (const item of section.items) {
      docsPaths.add(item.href);
    }
  }

  const lastModified = new Date();
  return [
    { url: SITE_URL, lastModified, changeFrequency: 'monthly', priority: 1 },
    ...Array.from(docsPaths).map((path) => ({
      url: `${SITE_URL}${path}`,
      lastModified,
      changeFrequency: 'weekly' as const,
      priority: 0.8,
    })),
  ];
}
