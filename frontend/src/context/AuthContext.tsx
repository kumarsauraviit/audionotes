"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  API,
  User,
  AuthTokens,
  authRequest,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  saveTokens,
  refreshAccessToken,
  authenticatedFetch,
} from "@/lib/auth";

type AuthContextType = {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  authFetch: typeof authenticatedFetch;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    let token = getAccessToken();
    if (!token && getRefreshToken()) {
      token = await refreshAccessToken();
    }
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const userData: User = await response.json();
        setUser(userData);
      } else if (response.status === 401) {
        const refreshedToken = await refreshAccessToken();
        if (refreshedToken) {
          const retryRes = await fetch(`${API}/api/auth/me`, {
            headers: { Authorization: `Bearer ${refreshedToken}` },
          });
          if (retryRes.ok) {
            const userData: User = await retryRes.json();
            setUser(userData);
          } else {
            clearTokens();
            setUser(null);
          }
        } else {
          clearTokens();
          setUser(null);
        }
      } else {
        clearTokens();
        setUser(null);
      }
    } catch {
      // Offline or network error
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const tokens = await authRequest<AuthTokens>("login", { email, password });
    saveTokens(tokens);
    await refreshUser();
  };

  const logout = async () => {
    const refreshToken = getRefreshToken();
    const accessToken = getAccessToken();
    if (accessToken && refreshToken) {
      try {
        await fetch(`${API}/api/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Clear local state regardless of network response
      }
    }
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user),
        isLoading,
        login,
        logout,
        refreshUser,
        authFetch: authenticatedFetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
