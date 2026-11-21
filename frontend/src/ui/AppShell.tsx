import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ArrowLeftRight, LogOut, Menu, X } from 'lucide-react';
import { cx } from './cx';

export type Area = 'app' | 'platform';

export interface NavItem {
  to: string;
  label: string;
  icon?: ReactNode;
  /** Match the path exactly (for index pages) */
  end?: boolean;
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

interface AppShellProps {
  area: Area;
  /** Org name in the workspace; "Platform" in the console */
  areaName: string;
  nav: NavGroup[];
  user: { name: string; email: string; detail?: string };
  onSignOut: () => void;
  /** Link to the other area, only for platform admins */
  switchTo?: { to: string; label: string };
  children: ReactNode;
}

/** The product mark: flat, no gradient. */
export function Mark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx(
        'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[4px] bg-ink font-display text-[17px] font-semibold leading-none text-canvas',
        className,
      )}
    >
      P
    </span>
  );
}

function SidebarContent({ area, areaName, nav, user, onSignOut, switchTo }: Omit<AppShellProps, 'children'>) {
  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-4 pt-5">
        <Link to={area === 'platform' ? '/platform' : '/app/interviews'} className="flex items-center gap-2.5">
          <Mark />
          <span className="font-display text-[19px] font-medium leading-tight text-ink">Presence View</span>
        </Link>
        <div className="mt-4">
          <p
            className={cx(
              'truncate text-meta font-medium',
              area === 'platform' ? 'uppercase tracking-[0.08em] text-accent' : 'text-muted',
            )}
            title={areaName}
          >
            {areaName}
          </p>
          {switchTo && (
            <Link
              to={switchTo.to}
              title={switchTo.label}
              className="mt-0.5 flex items-center gap-1 text-meta text-muted underline-offset-2 hover:text-ink hover:underline"
            >
              <ArrowLeftRight className="h-3 w-3 shrink-0" aria-hidden />
              <span className="truncate">Switch to {switchTo.label}</span>
            </Link>
          )}
        </div>
      </div>

      <nav aria-label="Main" className="flex-1 overflow-y-auto px-2">
        {nav.map((group, gi) => (
          <div key={gi} className="mb-4">
            {group.label && (
              <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted">{group.label}</p>
            )}
            <ul className="space-y-px">
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      cx(
                        'flex h-8 items-center gap-2.5 rounded-ui px-2 text-body transition-colors',
                        isActive
                          ? 'bg-surface font-medium text-ink shadow-[inset_2px_0_0_rgb(var(--c-accent))]'
                          : 'text-muted hover:bg-surface/60 hover:text-ink',
                      )
                    }
                  >
                    {item.icon && (
                      <span className="flex h-4 w-4 items-center justify-center [&>svg]:h-4 [&>svg]:w-4">
                        {item.icon}
                      </span>
                    )}
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-line px-4 py-3">
        <p className="truncate text-body font-medium text-ink">{user.name}</p>
        <p className="truncate text-meta text-muted">{user.detail ?? user.email}</p>
        <button
          type="button"
          onClick={onSignOut}
          className="mt-2 inline-flex items-center gap-1.5 text-meta text-muted hover:text-ink"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden />
          Sign out
        </button>
      </div>
    </div>
  );
}

/**
 * Sidebar + content. Below 900 px the sidebar becomes a top bar with a menu.
 * Sets data-area, which switches the palette (src/ui/tokens.css).
 */
export function AppShell(props: AppShellProps) {
  const { area, children, ...sidebar } = props;
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div data-area={area} className="min-h-screen min-[900px]:flex">
      <a
        href="#main"
        className="sr-only z-50 bg-surface px-3 py-2 text-body focus:not-sr-only focus:fixed focus:left-2 focus:top-2"
      >
        Skip to content
      </a>

      {/* Narrow: top bar */}
      <div className="sticky top-0 z-30 flex h-12 items-center justify-between border-b border-line bg-canvas px-4 min-[900px]:hidden">
        <Link to={area === 'platform' ? '/platform' : '/app/interviews'} className="flex items-center gap-2">
          <Mark className="h-6 w-6 text-[15px]" />
          <span className="font-display text-lead text-ink">Presence View</span>
        </Link>
        <button
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          className="flex h-8 w-8 items-center justify-center text-ink"
        >
          {menuOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
        </button>
      </div>

      <aside
        id="sidebar"
        className={cx(
          'border-line bg-canvas',
          'min-[900px]:sticky min-[900px]:top-0 min-[900px]:block min-[900px]:h-screen min-[900px]:w-sidebar min-[900px]:shrink-0 min-[900px]:border-r',
          menuOpen ? 'fixed inset-x-0 bottom-0 top-12 z-20 block border-t' : 'hidden',
        )}
      >
        <SidebarContent area={area} {...sidebar} />
      </aside>

      <main id="main" tabIndex={-1} className="min-w-0 flex-1 focus:outline-none">
        <div className="mx-auto max-w-content px-4 py-8 sm:px-8 sm:py-10">{children}</div>
      </main>
    </div>
  );
}
