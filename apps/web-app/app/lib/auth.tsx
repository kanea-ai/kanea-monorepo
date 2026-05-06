'use client';

import { useRouter } from 'next/navigation';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { TOKEN_STORAGE_KEY, authApi, type LoginPayload, type RegisterPayload } from './api';

interface AuthContextValue {
  token: string | null;
  isReady: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // `isReady` gates UI on the first read from localStorage. SSR renders with
  // null, then the effect rehydrates — without this, protected pages flash
  // the login redirect before the real token is observed.
  const [token, setToken] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setToken(window.localStorage.getItem(TOKEN_STORAGE_KEY));
    setIsReady(true);
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const res = await authApi.login(payload);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
    setToken(res.access_token);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await authApi.register(payload);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
    setToken(res.access_token);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    router.replace('/login');
  }, [router]);

  const value = useMemo(
    () => ({ token, isReady, login, register, logout }),
    [token, isReady, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

/**
 * Redirects unauthenticated users to /login. Returns `true` once the auth
 * state has been read from storage and a token is present, so callers can
 * gate rendering until then.
 */
export function useRequireAuth(): boolean {
  const { token, isReady } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isReady && !token) router.replace('/login');
  }, [isReady, token, router]);

  return isReady && Boolean(token);
}
