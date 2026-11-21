/**
 * Learner sign-in (and sign-up when the server allows it).
 * After sign-in: back to the page that sent them here, or /study.
 */

import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { getAuthConfig, login, signup } from '../services/authApi';
import { useQuery } from '@tanstack/react-query';
import { homeFor } from '../areas/shared/routing';
import { Button, Field, Input, Mark } from '../ui';
import type { AuthUser } from '../types';

/** Only same-site paths, so a crafted ?next= can't send users to another site */
function safeNext(next: string | null): string | null {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/login') ? next : null;
}

export function LoginPage() {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const expired = params.get('expired') === '1';
  const config = useQuery({ queryKey: ['auth-config'], queryFn: getAuthConfig, staleTime: 5 * 60_000 });

  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const destination = (u: AuthUser) => next ?? homeFor(u);

  if (!loading && user) {
    return <Navigate to={destination(user)} replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await signup({ name, email, password });
      }
      const me = await refresh();
      if (me) navigate(destination(me), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setBusy(false);
    }
  };

  const signupEnabled = !!config.data?.signup_enabled;

  return (
    <div data-area="app" className="flex min-h-screen flex-col">
      <header className="px-6 py-5 sm:px-10">
        <span className="inline-flex items-center gap-2.5">
          <Mark />
          <span className="font-display text-[19px] text-ink">Presence View</span>
        </span>
      </header>

      <main className="flex flex-1 items-start justify-center px-6 pb-16 pt-[8vh] sm:px-10">
        <div className="w-full max-w-[380px]">
          <h1 className="font-display text-h2 text-ink">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
          <p className="mt-2 text-lead text-muted">
            {mode === 'login'
              ? 'Sign in to study with your buddy.'
              : 'One account, your own study sessions.'}
          </p>

          {expired && mode === 'login' && (
            <p role="status" className="mt-6 border-l-2 border-warn bg-warn/5 px-3 py-2 text-body text-ink">
              Your session ended. Sign in again to continue where you were.
            </p>
          )}

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            {mode === 'signup' && (
              <>
                <Field label="Your name">
                  {(p) => (
                    <Input
                      id={p.id}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      autoComplete="name"
                    />
                  )}
                </Field>
              </>
            )}
            <Field label="Email">
              {(p) => (
                <Input
                  id={p.id}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              )}
            </Field>
            <Field label="Password" hint={mode === 'signup' ? 'At least 10 characters.' : undefined}>
              {(p) => (
                <Input
                  id={p.id}
                  aria-describedby={p.describedBy}
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  minLength={mode === 'signup' ? 10 : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              )}
            </Field>

            {error && (
              <p role="alert" className="text-body text-bad">
                {error}
              </p>
            )}

            <Button type="submit" variant="primary" loading={busy} className="w-full">
              {mode === 'login' ? 'Sign in' : 'Create organization'}
            </Button>
          </form>

          {signupEnabled && (
            <p className="mt-6 text-body text-muted">
              {mode === 'login' ? 'New here? ' : 'Already have an account? '}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'login' ? 'signup' : 'login');
                  setError(null);
                }}
                className="font-medium text-accent underline-offset-2 hover:underline"
              >
                {mode === 'login' ? 'Create an organization' : 'Sign in'}
              </button>
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
