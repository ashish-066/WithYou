/**
 * The app frame: content + navigation. A bottom tab bar on phones, a side rail
 * from tablet width up. Sessions (/session) run full screen, outside this frame.
 */
import { NavLink, Outlet } from 'react-router-dom';
import { BarChart3, BookOpen, History, Home, UserRound } from 'lucide-react';

import { cx } from '@/ui/cx';
import { usePrefs } from './prefs';
import { strings } from './strings';

export function AppShell() {
  const { language } = usePrefs();
  const t = strings(language);
  const items = [
    { to: '/', label: t.nav.home, Icon: Home, end: true },
    { to: '/history', label: t.nav.history, Icon: History },
    { to: '/progress', label: t.nav.progress, Icon: BarChart3 },
    { to: '/me', label: t.nav.profile, Icon: UserRound },
  ];

  return (
    <div data-area="app" className="min-h-[100dvh] bg-canvas text-ink md:flex">
      {/* Side rail (tablet / desktop) */}
      <nav aria-label="Main" className="hidden w-56 shrink-0 flex-col gap-1 border-r border-line bg-surface p-4 md:flex">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-on">
            <BookOpen size={18} aria-hidden />
          </span>
          <span className="font-display text-h3">Study Buddy</span>
        </div>
        {items.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cx(
                'flex items-center gap-3 rounded-ui px-3 py-2.5 text-lead',
                isActive ? 'bg-accent/10 text-accent' : 'text-muted hover:text-ink',
              )
            }
          >
            <Icon size={20} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>

      <main className="mx-auto w-full max-w-2xl px-4 pb-28 pt-[max(20px,env(safe-area-inset-top))] md:px-8 md:pb-12">
        <Outlet />
      </main>

      {/* Bottom tab bar (phones) */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {items.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cx(
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-meta',
                isActive ? 'text-accent' : 'text-muted',
              )
            }
          >
            <Icon size={22} aria-hidden />
            <span className="max-w-full truncate px-1">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
