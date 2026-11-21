import { Outlet, useNavigate } from 'react-router-dom';
import { Activity, Building2, Code2, Cpu, FlaskConical, Inbox, ListChecks, ScrollText } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { AppShell, type NavGroup } from '@/ui';
import { useAuthConfig } from '../shared/data';

/** Platform console: platform admins only (RequirePlatformAdmin sits above this). */
export function PlatformLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const config = useAuthConfig();
  if (!user) return null;

  const nav: NavGroup[] = [
    {
      items: [
        { to: '/platform', label: 'Health', icon: <Activity />, end: true },
        { to: '/platform/organizations', label: 'Organizations', icon: <Building2 /> },
        { to: '/platform/interviews', label: 'All interviews', icon: <ListChecks /> },
        { to: '/platform/problems', label: 'Problem library', icon: <Code2 /> },
      ],
    },
    {
      label: 'Operations',
      items: [
        { to: '/platform/workers', label: 'Workers', icon: <Cpu /> },
        { to: '/platform/queues', label: 'Queues', icon: <Inbox /> },
        { to: '/platform/audit', label: 'Audit log', icon: <ScrollText /> },
      ],
    },
  ];
  if (config.data?.demo_enabled) {
    nav.push({ label: 'Tools', items: [{ to: '/platform/demo', label: 'Demo', icon: <FlaskConical /> }] });
  }

  return (
    <AppShell
      area="platform"
      areaName="Platform"
      nav={nav}
      user={{ name: user.name, email: user.email, detail: 'Platform admin' }}
      onSignOut={async () => {
        await logout();
        navigate('/login', { replace: true });
      }}
      switchTo={{ to: '/app/interviews', label: user.org_name || 'Workspace' }}
    >
      <Outlet />
    </AppShell>
  );
}
