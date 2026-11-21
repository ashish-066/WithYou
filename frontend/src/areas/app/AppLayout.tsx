import { Outlet, useNavigate } from 'react-router-dom';
import { Inbox, ListChecks, Mail, Trophy, Users } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { AppShell, type NavGroup } from '@/ui';
import { isOrgAdmin } from '../shared/routing';

/** Organization workspace: recruiters and org admins (platform admins too, for their own org). */
export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null; // RequireAuth sits above this

  const nav: NavGroup[] = [
    {
      items: [
        { to: '/app/interviews', label: 'Interviews', icon: <ListChecks /> },
        { to: '/app/invites', label: 'Invites', icon: <Mail /> },
        { to: '/app/roles', label: 'Job roles', icon: <Inbox /> },
        { to: '/app/rankings', label: 'Rankings', icon: <Trophy /> },
      ],
    },
  ];
  if (isOrgAdmin(user)) {
    nav.push({ label: 'Organization', items: [{ to: '/app/team', label: 'Team', icon: <Users /> }] });
  }

  return (
    <AppShell
      area="app"
      areaName={user.org_name || 'Your organization'}
      nav={nav}
      user={{ name: user.name, email: user.email, detail: user.role === 'admin' ? 'Admin' : 'Recruiter' }}
      onSignOut={async () => {
        await logout();
        navigate('/login', { replace: true });
      }}
      switchTo={user.is_platform_admin ? { to: '/platform', label: 'Platform' } : undefined}
    >
      <Outlet />
    </AppShell>
  );
}
