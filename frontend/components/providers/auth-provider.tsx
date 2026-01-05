"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { tokenResponseSchema, type TokenResponse } from "@/types/auth";
import { clearSession, readSession, writeSession, STORAGE_KEY } from "@/lib/session";

type AuthContextValue = {
  session: TokenResponse | null;
  isAuthenticated: boolean;
  loading: boolean;
  saveSession: (session: TokenResponse) => void;
  logout: () => void;
  setActiveTenant: (tenant: TokenResponse["tenant"] | null) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [session, setSession] = useState<TokenResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const hydrateSession = useCallback(() => {
    const stored = readSession();
    setSession(stored);
    setLoading(false);
  }, []);

  useEffect(() => {
    hydrateSession();
  }, [hydrateSession]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) {
        return;
      }

      if (!event.newValue) {
        setSession(null);
        return;
      }

      try {
        const parsedValue = JSON.parse(event.newValue);
        const parsed = tokenResponseSchema.safeParse(parsedValue);
        if (!parsed.success) {
          setSession(null);
          return;
        }
        setSession(parsed.data);
      } catch (error) {
        console.error("Failed to parse session change event", error);
        setSession(null);
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const saveSession = useCallback((nextSession: TokenResponse) => {
    writeSession(nextSession);
    setSession(nextSession);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  const setActiveTenant = useCallback((tenant: TokenResponse["tenant"] | null) => {
    setSession((current) => {
      if (!current) {
        return current;
      }
      const updated = { ...current, tenant: tenant ?? null };
      writeSession(updated);
      return updated;
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: Boolean(session?.access_token),
      loading,
      saveSession,
      logout,
      setActiveTenant,
    }),
    [session, loading, saveSession, logout, setActiveTenant]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
