import { getToken, setToken } from './tokenStore';

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function extractDetailMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  // FastAPI 422 validation errors: { detail: [{ msg, loc, ... }, ...] }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  return fallback;
}

/** Raw fetch wrapper: attaches auth header, handles 401 centrally, throws ApiError on failure. */
export async function apiFetchRaw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...authHeaders(),
    ...(init.headers as Record<string, string> | undefined),
  };

  const resp = await fetch(path, { ...init, headers });

  if (resp.status === 401) {
    // Token expired/invalid - clear it so AuthContext/ProtectedRoute react.
    setToken(null);
  }

  if (!resp.ok) {
    let detail: unknown;
    try {
      const body = await resp.clone().json();
      detail = body?.detail;
    } catch {
      // response wasn't JSON
    }
    const message = extractDetailMessage(detail, resp.statusText || 'Request failed');
    throw new ApiError(resp.status, message, detail);
  }

  return resp;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  const resp = await apiFetchRaw(path, { ...init, headers });
  if (resp.status === 204) {
    return undefined as T;
  }
  return resp.json() as Promise<T>;
}
