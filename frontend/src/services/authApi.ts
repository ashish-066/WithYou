/**
 * Auth API: learner sign-in.
 *
 * The session lives in an HttpOnly cookie set by the server, so requests need
 * no token handling: same-origin fetches send the cookie automatically.
 */

import type { AuthUser } from '../types';

const API_BASE = '/api/auth';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json', ...init?.headers } : init?.headers,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = typeof error.detail === 'string' ? error.detail : `Request failed (${response.status})`;
    const err = new Error(detail) as Error & { status?: number };
    err.status = response.status;
    throw err;
  }
  return response.json();
}

/** Current user, or null when not signed in. */
export async function getMe(): Promise<AuthUser | null> {
  try {
    return await request<AuthUser>('/me');
  } catch (err) {
    if ((err as { status?: number }).status === 401) return null;
    throw err;
  }
}

export function login(email: string, password: string): Promise<AuthUser> {
  return request('/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export function signup(params: {
  name: string;
  email: string;
  password: string;
}): Promise<AuthUser> {
  return request('/signup', { method: 'POST', body: JSON.stringify(params) });
}

export async function logout(): Promise<void> {
  await request('/logout', { method: 'POST' });
}

export function getAuthConfig(): Promise<{ signup_enabled: boolean }> {
  return request('/config');
}
