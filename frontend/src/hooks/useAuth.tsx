/**
 * Signed-in learner state.
 */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getMe, logout as apiLogout } from '../services/authApi';
import type { AuthUser } from '../types';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  /** Re-read the session (after login/signup) */
  refresh: () => Promise<AuthUser | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await getMe();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** Renders children only for signed-in users; otherwise sends them to /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    // Blank page in the workspace colours while the session is checked
    return <div data-area="app" className="min-h-screen" />;
  }
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}
