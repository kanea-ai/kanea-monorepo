'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { AuthProvider } from './lib/auth';

export function Providers({ children }: { children: React.ReactNode }) {
  // One QueryClient per browser session — same pattern the web-app
  // uses. Stale-while-revalidate semantics with a short default stale
  // time so the workspace list refreshes promptly after a
  // suspend/restore.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
