'use client';

// Minimal auth context for the back-office. The admin app reuses the
// same /auth/login flow as the customer-facing web-app — we just
// store the resulting JWT and use it on /admin/* calls. The api's
// SuperadminDep cross-checks ``users.is_superadmin`` on every
// request, so a non-elevated token can authenticate but every admin
// route still 403s.

import { useRouter } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { authApi, TOKEN_STORAGE_KEY } from './api';

interface AuthContextValue {
  token: string | null;
  isReady: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setToken(window.localStorage.getItem(TOKEN_STORAGE_KEY));
    setIsReady(true);
  }, []);

  const persist = useCallback((value: string | null) => {
    if (typeof window === 'undefined') return;
    if (value) window.localStorage.setItem(TOKEN_STORAGE_KEY, value);
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(value);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const out = await authApi.login({ email, password });
      // Two response shapes from /auth/login:
      //   - single-workspace user: { access_token, expires_in }
      //   - multi-workspace user:  { select_token, workspaces[] }
      // We don't care which workspace the bearer is for — the admin
      // API doesn't read workspace context — so we just pick the
      // first one in the multi-workspace case.
      if (out.access_token) {
        persist(out.access_token);
        return;
      }
      if (out.select_token && out.workspaces && out.workspaces.length > 0) {
        // Persist the select token briefly so the swap call carries it.
        persist(out.select_token);
        const swap = await authApi.selectWorkspace({
          workspace_id: out.workspaces[0].workspace_id,
        });
        persist(swap.access_token);
        return;
      }
      throw new Error('login did not return a usable token');
    },
    [persist],
  );

  const logout = useCallback(() => persist(null), [persist]);

  const value = useMemo(() => ({ token, isReady, login, logout }), [token, isReady, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

/** Redirects unauthenticated visitors to /login. Returns true when
 *  auth state has been hydrated AND a token is present. */
export function useRequireAuth(): boolean {
  const { token, isReady } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (isReady && !token) router.replace('/login');
  }, [isReady, token, router]);
  return isReady && !!token;
}
