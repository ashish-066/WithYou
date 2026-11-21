/**
 * The app frame: content + navigation. A bottom tab bar on phones, a side rail
 * from tablet width up. Sessions (/session) run full screen, outside this frame.
 */
import { NavLink, Outlet } from 'react-router-dom';
import { BarChart3, History, Home, UserRound } from 'lucide-react';

import { cx } from '@/ui/cx';
import { Buddy } from './Buddy';
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
    <div data-area="notebook" className="paper min-h-[100dvh] text-ink md:flex">
      {/* Side rail (tablet / desktop) */}
      <nav aria-label="Main" className="hidden w-60 shrink-0 flex-col gap-1 border-r-2 border-ink/80 bg-surface p-4 md:flex">
        <div className="mb-6 flex flex-col items-center gap-1 px-2 pt-2">
          <Buddy mood="happy" size={84} />
          <span className="font-display text-h3 font-bold">Study Buddy</span>
          <span className="font-hand text-[20px] leading-5 text-terracotta">പഠിപ്പ് കൂട്ടുകാരൻ</span>
        </div>
        {items.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cx(
                'flex items-center gap-3 px-3 py-2.5 text-lead',
                isActive ? 'sketch-soft bg-turmeric-soft font-semibold text-ink' : 'text-muted hover:text-ink',
              )
            }
          >
            <Icon size={20} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>

      <main className="margin-line mx-auto w-full max-w-2xl px-5 pb-28 pt-[max(20px,env(safe-area-inset-top))] md:px-10 md:pb-12">
        <Outlet />
      </main>

      {/* Bottom tab bar (phones) */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t-2 border-ink/80 bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {items.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cx(
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-meta',
                isActive ? 'font-semibold text-accent' : 'text-muted',
              )
            }
          >
            <Icon size={22} aria-hidden />
            <span className="whitespace-nowrap px-1 leading-6">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
