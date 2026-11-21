/**
 * One way to call the API from the new UI.
 *
 * - Same-origin `/api/...`: the session is an HttpOnly cookie, sent automatically.
 * - Every failure is an ApiError with the HTTP status and a readable message
 *   (FastAPI's `detail`, including 422 validation lists).
 * - A 401 on anything but the auth endpoints means the session ended: send the
 *   person to sign in and bring them back afterwards.
 */

export const API_BASE = '/api';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  get isNotFound() {
    return this.status === 404;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** Don't redirect to sign-in on 401 (used by the auth calls themselves) */
  allowUnauthenticated?: boolean;
}

function buildUrl(path: string, query?: Query): string {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/** FastAPI errors: {"detail": "text"} or {"detail": [{"loc": [...], "msg": "..."}]} */
function messageFrom(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: string };
    const field = Array.isArray(first.loc) ? first.loc.filter((p) => p !== 'body').join('.') : '';
    return field ? `${field}: ${first.msg ?? 'invalid'}` : (first.msg ?? 'Invalid request');
  }
  if (status === 403) return 'You don’t have access to this.';
  if (status === 404) return 'Not found.';
  if (status === 429) return 'Too many requests. Wait a moment and try again.';
  if (status >= 500) return 'Something went wrong on the server. Try again in a moment.';
  return `Request failed (${status})`;
}

let redirectingToLogin = false;

function sendToLogin() {
  if (redirectingToLogin || window.location.pathname === '/login') return;
  redirectingToLogin = true;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}&expired=1`);
}

async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, opts.query), {
      method,
      signal: opts.signal,
      credentials: 'same-origin',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError('Can’t reach the server. Check your connection.', 0);
  }

  if (response.status === 401 && !opts.allowUnauthenticated) {
    sendToLogin();
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(messageFrom(response.status, body), response.status, body);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'body'>) => request<T>('GET', path, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, { ...opts, body }),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PATCH', path, { ...opts, body }),
  delete: <T>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, opts),
};

/** Readable message for any thrown value, for error states and toasts. */
export function errorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
