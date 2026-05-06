'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

// Placeholder home page. The Dashboard view replaces this in the next
// commit; until then we keep the user landing on the board so the app
// doesn't 404 on `/`.
export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/board');
  }, [router]);
  return null;
}
