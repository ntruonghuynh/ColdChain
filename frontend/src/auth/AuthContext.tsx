import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setBearerToken } from '../api/client';
import type { AuthIdentity } from '../api/client';

interface AuthContextValue {
  identity: AuthIdentity | null;
  busy: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);
  const [busy, setBusy] = useState(false);

  const logout = useCallback(() => {
    setBearerToken(null);
    setIdentity(null);
  }, []);

  useEffect(() => {
    const onUnauthorized = () => logout();
    window.addEventListener('coldchain:unauthorized', onUnauthorized);
    return () => window.removeEventListener('coldchain:unauthorized', onUnauthorized);
  }, [logout]);

  const login = useCallback(async (username: string, password: string) => {
    setBusy(true);
    try {
      const result = await api.login(username, password);
      setBearerToken(result.data.access_token);
      try {
        const me = await api.me();
        setIdentity(me.data);
      } catch (error) {
        setBearerToken(null);
        throw error;
      }
    } finally {
      setBusy(false);
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    identity,
    busy,
    login,
    logout,
    hasRole: (role) => identity?.roles.includes(role) ?? false,
  }), [identity, busy, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
