import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import * as authApi from '../api/auth';
import { getToken, setToken as persistToken, onTokenChange } from '../api/tokenStore';
import type { CurrentUser } from '../types/auth';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

interface AuthContextValue {
  user: CurrentUser | null;
  token: string | null;
  status: AuthStatus;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [token, setTokenState] = useState<string | null>(getToken());
  const [status, setStatus] = useState<AuthStatus>('loading');

  const refreshUser = useCallback(async () => {
    const currentToken = getToken();
    if (!currentToken) {
      setUser(null);
      setStatus('unauthenticated');
      return;
    }
    try {
      const currentUser = await authApi.me();
      setUser(currentUser);
      setStatus('authenticated');
    } catch {
      persistToken(null);
      setUser(null);
      setStatus('unauthenticated');
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    // Fires when apiFetchRaw clears the token on a 401, or from other tabs/logout calls.
    return onTokenChange((newToken) => {
      setTokenState(newToken);
      if (!newToken) {
        setUser(null);
        setStatus('unauthenticated');
      }
    });
  }, []);

  const loginWithToken = useCallback(async (newToken: string) => {
    persistToken(newToken);
    setTokenState(newToken);
    await refreshUser();
  }, [refreshUser]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // stateless JWT - ignore network errors on logout
    }
    persistToken(null);
    setUser(null);
    setStatus('unauthenticated');
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, status, loginWithToken, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
