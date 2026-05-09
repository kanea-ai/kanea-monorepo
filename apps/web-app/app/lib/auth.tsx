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

import {
  TOKEN_STORAGE_KEY,
  authApi,
  setUnauthorizedHandler,
  type LoginPayload,
  type LoginResponse,
  type RegisterPayload,
  type SelectWorkspacePayload,
  type WorkspaceOption,
} from './api';

// Login is branched in Phase 1: 1 workspace -> straight token, >1 ->
// caller must render a picker, then call `selectWorkspace` to exchange
// the short-lived selection token for the final access token.
export type LoginResult =
  | { kind: 'token' }
  | { kind: 'selection'; selectionToken: string; workspaces: WorkspaceOption[] };

interface AuthContextValue {
  token: string | null;
  isReady: boolean;
  login: (payload: LoginPayload) => Promise<LoginResult>;
  selectWorkspace: (payload: SelectWorkspacePayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  /** Hydrate the AuthContext after an OAuth round-trip drops a token in the URL. */
  setTokenFromOAuth: (token: string) => void;
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

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    // Preserve the current path as `?next=` so post-login lands the user
    // back where they were when their session expired.
    if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
      const here = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(here)}`);
    } else {
      router.replace('/login');
    }
  }, [router]);

  // Wire the 401 interceptor up exactly once. The api module calls back
  // here whenever an authenticated endpoint returns 401 — regardless of
  // whether the request went through fetch() directly or through the
  // typed request<T>() helper.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (payload: LoginPayload): Promise<LoginResult> => {
    const res: LoginResponse = await authApi.login(payload);
    if (res.requires_selection) {
      // Don't store anything yet — the caller must complete the
      // selection step before we have a usable access token.
      return {
        kind: 'selection',
        selectionToken: res.selection_token!,
        workspaces: res.workspaces ?? [],
      };
    }
    window.localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token!);
    setToken(res.access_token);
    return { kind: 'token' };
  }, []);

  const selectWorkspace = useCallback(async (payload: SelectWorkspacePayload) => {
    const res = await authApi.selectWorkspace(payload);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
    setToken(res.access_token);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await authApi.register(payload);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
    setToken(res.access_token);
  }, []);

  const setTokenFromOAuth = useCallback((newToken: string) => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
    setToken(newToken);
  }, []);

  const value = useMemo(
    () => ({
      token,
      isReady,
      login,
      selectWorkspace,
      register,
      logout,
      setTokenFromOAuth,
    }),
    [token, isReady, login, selectWorkspace, register, logout, setTokenFromOAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export interface CurrentPrincipal {
  member_id: string;
  workspace_id: string;
  role: 'WORKSPACE_OWNER' | 'WORKSPACE_ADMIN' | 'WORKSPACE_MEMBER';
  type: 'HUMAN' | 'AGENT';
  scope: string;
}

/**
 * Decode the JWT payload to surface the caller's identity + role.
 *
 * The signature is not verified here — that's the server's job. We
 * use this only for cosmetic / RBAC-aware UI gating (e.g. showing a
 * "Create team" button to admins). Every privileged action still goes
 * through the api, which rejects with 403 on its own.
 */
export function useCurrentPrincipal(): CurrentPrincipal | null {
  const { token, isReady } = useAuth();
  return useMemo(() => {
    if (!isReady || !token) return null;
    try {
      const [, payload] = token.split('.');
      if (!payload) return null;
      const padded = payload.replace(/-/g, '+').replace(/_/g, '/');
      const json = JSON.parse(atob(padded + '='.repeat((4 - (padded.length % 4)) % 4)));
      return {
        member_id: String(json.sub),
        workspace_id: String(json.workspace_id),
        role: json.role ?? 'WORKSPACE_MEMBER',
        type: json.type ?? 'HUMAN',
        scope: json.scope ?? 'human',
      };
    } catch {
      return null;
    }
  }, [token, isReady]);
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
