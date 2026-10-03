export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type User = {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
};

export type AuthTokens = {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
};

const ACCESS_KEY = "audio-notes.access-token";
const REFRESH_KEY = "audio-notes.refresh-token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY) || sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY) || sessionStorage.getItem(REFRESH_KEY);
}

export function saveTokens(tokens: AuthTokens) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

export async function authRequest<T>(path: string, payload: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  let response: Response;
  try {
    response = await fetch(`${API}/api/auth/${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("Could not reach the server. Please verify the backend is running.");
  }

  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = result.detail;
    throw new Error(Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join(" ") : detail || "Request failed.");
  }
  return result as T;
}

export async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const response = await fetch(`${API}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) {
      clearTokens();
      return null;
    }
    const data: AuthTokens = await response.json();
    saveTokens(data);
    return data.access_token;
  } catch {
    return null;
  }
}

export async function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let token = getAccessToken();
  const options = { ...init };
  const reqHeaders = new Headers(options.headers || {});

  if (token && !reqHeaders.has("Authorization")) {
    reqHeaders.set("Authorization", `Bearer ${token}`);
  }
  options.headers = reqHeaders;

  let response: Response;
  try {
    response = await fetch(input, options);
  } catch (err) {
    throw new Error("Network error connecting to API.");
  }

  // If 401 Unauthorized, attempt refresh token rotation once
  if (response.status === 401 && getRefreshToken()) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      const retryHeaders = new Headers(init?.headers || {});
      retryHeaders.set("Authorization", `Bearer ${newToken}`);
      return fetch(input, { ...init, headers: retryHeaders });
    }
  }

  return response;
}
