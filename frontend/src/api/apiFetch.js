import { updateToken, getToken } from "./tokenBus";

const BASE = "/api/v1";

let refreshPromise = null;

export function refreshSession() {
  if (refreshPromise) return refreshPromise;
  
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error("Refresh failed");
      const data = await res.json();
      updateToken(data.access_token);
      return data.access_token;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401 && path !== "/auth/login" && path !== "/auth/refresh") {
    try {
      const newToken = await refreshSession();
      const retryHeaders = { ...headers, Authorization: `Bearer ${newToken}` };
      res = await fetch(`${BASE}${path}`, { ...options, headers: retryHeaders });
    } catch (error) {
      updateToken(null);
      throw new Error("Сессия истекла");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.message || `Ошибка API: HTTP ${res.status}`);
  }

  return res;
}
