/**
 * Auth context backed by the `/api/v1/auth/me` endpoint.
 *
 * The session is held server-side in an httpOnly `pwc_session` cookie set by
 * the HF OAuth callback (see `backend/routers/auth.py`). The frontend simply
 * asks `/auth/me` whether the cookie is valid and caches the result in a
 * React context so any component can read `useAuth()`.
 *
 * A custom `pwc:auth-stale` window event lets the canonical API transport
 * tell us when a write returned 401 so we can clear local state.
 */

import React from "react";
import posthog from "posthog-js";
import { useQueryClient } from "@tanstack/react-query";

import { authApi, type AuthUser } from "./api/auth";
import { authUrl } from "./apiUrl";

export type { AuthUser } from "./api/auth";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

const AUTH_STALE_EVENT = "pwc:auth-stale";
const POSTHOG_SIGNUP_COOKIE = "pwc_posthog_signup";

function consumeSignupMarker(): boolean {
  if (!document.cookie.split("; ").includes(`${POSTHOG_SIGNUP_COOKIE}=1`)) {
    return false;
  }
  document.cookie = `${POSTHOG_SIGNUP_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax`;
  return true;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = React.useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const queryClient = useQueryClient();
  const previousUserRef = React.useRef<AuthUser | null>(null);

  const refresh = React.useCallback(async () => {
    setIsLoading(true);
    const next = await authApi.getCurrentUser();
    setUser(next);
    setIsLoading(false);
  }, []);

  const logout = React.useCallback(async () => {
    const endpoint = authUrl("/api/v1/auth/logout");
    if (
      new URL(endpoint, window.location.origin).origin !==
      window.location.origin
    ) {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = `${endpoint}?return_to=${encodeURIComponent(window.location.href)}`;
      document.body.appendChild(form);
      form.submit();
      return;
    }
    await authApi.logout();
    setUser(null);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (!import.meta.env.VITE_POSTHOG_PROJECT_TOKEN) return;
    if (!user) {
      posthog.reset();
      return;
    }

    posthog.identify(user.hf_subject, { hf_username: user.username });
    if (consumeSignupMarker()) {
      posthog.capture("signup_completed", { auth_provider: "huggingface" });
    }
  }, [user]);

  // Drop the signed-out user's cached data (bookmarks, follows, sessions).
  React.useEffect(() => {
    if (previousUserRef.current && !user) void queryClient.resetQueries();
    previousUserRef.current = user;
  }, [queryClient, user]);

  React.useEffect(() => {
    const handler = () => {
      setUser(null);
    };
    window.addEventListener(AUTH_STALE_EVENT, handler);
    return () => window.removeEventListener(AUTH_STALE_EVENT, handler);
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({ user, isLoading, refresh, logout }),
    [user, isLoading, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return ctx;
}

/** Like useAuth, but usable in components that also render outside an <AuthProvider>. */
export function useOptionalAuth(): AuthContextValue | null {
  return React.useContext(AuthContext);
}
