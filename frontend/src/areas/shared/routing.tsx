/**
 * Who goes where. Two areas:
 *   /app/...       organization workspace (recruiters, org admins)
 *   /platform/...  platform console (platform admins only)
 * A page someone may not use answers "not found", so its existence isn't revealed.
 */
import type { ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import type { AuthUser } from '@/types';
import { buttonClass, Mark } from '@/ui';

export const homeFor = (user: AuthUser) => (user.is_platform_admin ? '/platform' : '/app/interviews');

export const isOrgAdmin = (user: AuthUser | null) => !!user && (user.role === 'admin' || user.is_platform_admin);

/** Blank page in the workspace colours while the session is checked. */
export function Blank() {
  return <div data-area="app" className="min-h-screen" />;
}

/** `/home`: the right home for whoever is signed in. (`/` is the public landing page.) */
export function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Blank />;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homeFor(user)} replace />;
}

export function RequireOrgAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return isOrgAdmin(user) ? <>{children}</> : <NotFoundContent />;
}

export function RequirePlatformAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Blank />;
  return user?.is_platform_admin ? <>{children}</> : <NotFound />;
}

/** "Not found" inside an area layout (the sidebar stays). */
export function NotFoundContent() {
  const { user } = useAuth();
  const location = useLocation();
  return (
    <div className="max-w-lg py-10">
      <p className="font-mono text-meta text-muted">404</p>
      <h1 className="mt-2 font-display text-h2 text-ink">Page not found</h1>
      <p className="mt-3 text-lead text-muted">
        There’s nothing at <span className="font-mono text-body text-ink">{location.pathname}</span>. It may have moved,
        or the link may be wrong.
      </p>
      <Link to={user ? homeFor(user) : '/login'} className={buttonClass('secondary', 'md', 'mt-6')}>
        {user ? 'Go to your home page' : 'Sign in'}
      </Link>
    </div>
  );
}

/** Standalone "not found" for URLs outside any area. */
export function NotFound() {
  return (
    <div data-area="app" className="min-h-screen">
      <div className="mx-auto max-w-content px-4 py-6 sm:px-8">
        <a href="/" className="inline-flex items-center gap-2.5">
          <Mark />
          <span className="font-display text-[19px] text-ink">Presence View</span>
        </a>
        <NotFoundContent />
      </div>
    </div>
  );
}

/** Old /dashboard links keep working. */
export function LegacyRedirect({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={to + location.search} replace />;
}
