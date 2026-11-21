/**
 * Routes.
 *   /              public landing page (static, served by nginx from public/landing)
 *   /home          sends you to your workspace, or to /login when signed out
 *   /interview     candidate (public, via invite link)
 *   /login         sign-in
 *   /app/...       organization workspace (recruiters, org admins)
 *   /platform/...  platform console (platform admins only)
 *   /dashboard/... old URLs, redirected
 * Plan: context/dashboard_rebuild_plan.md, section 3.
 */

import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';

import { AuthProvider, RequireAuth } from './hooks/useAuth';
import { InterviewPage } from './pages/InterviewPage';
import { LoginPage } from './pages/LoginPage';
import { AppLayout } from './areas/app/AppLayout';
import { InterviewsPage } from './areas/app/InterviewsPage';
import { InterviewReportPage } from './areas/app/InterviewReportPage';
import { InvitesPage } from './areas/app/InvitesPage';
import { RolesPage } from './areas/app/RolesPage';
import { TeamPage } from './areas/app/TeamPage';
import { RankingsPage } from './areas/app/RankingsPage';
import { PlatformLayout } from './areas/platform/PlatformLayout';
import { HealthPage } from './areas/platform/HealthPage';
import { AllInterviewsPage } from './areas/platform/AllInterviewsPage';
import { DemoPage } from './areas/platform/DemoPage';
import { OrganizationsPage } from './areas/platform/OrganizationsPage';
import { OrganizationPage } from './areas/platform/OrganizationPage';
import { WorkersPage } from './areas/platform/WorkersPage';
import { QueuesPage } from './areas/platform/QueuesPage';
import { AuditPage } from './areas/platform/AuditPage';
import { ProblemsPage } from './areas/platform/ProblemsPage';
import { ProblemEditorPage } from './areas/platform/ProblemEditorPage';
import {
  Home,
  LegacyRedirect,
  NotFound,
  NotFoundContent,
  RequireOrgAdmin,
  RequirePlatformAdmin,
} from './areas/shared/routing';

// Development-only reference of the new UI building blocks. In production builds
// import.meta.env.DEV is false, so the route and its code are left out entirely.
const UiReference = import.meta.env.DEV
  ? lazy(() => import('./areas/dev/UiReference').then((m) => ({ default: m.UiReference })))
  : null;

function OldSessionRedirect() {
  const { sessionId } = useParams();
  return <Navigate to={`/app/interviews/${encodeURIComponent(sessionId ?? '')}`} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* In production nginx serves the landing page at "/" before the app loads;
            this redirect only matters in dev and for in-app navigation. */}
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<Home />} />
        <Route path="/interview" element={<InterviewPage />} />
        <Route path="/login" element={<LoginPage />} />

        {UiReference && (
          <Route
            path="/app/_ui/*"
            element={
              <Suspense fallback={null}>
                <UiReference />
              </Suspense>
            }
          />
        )}

        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="interviews" replace />} />
          <Route path="interviews" element={<InterviewsPage />} />
          <Route path="interviews/:sessionId" element={<InterviewReportPage />} />
          <Route path="invites" element={<InvitesPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="rankings" element={<RankingsPage />} />
          <Route
            path="team"
            element={
              <RequireOrgAdmin>
                <TeamPage />
              </RequireOrgAdmin>
            }
          />
          <Route path="*" element={<NotFoundContent />} />
        </Route>

        <Route
          path="/platform"
          element={
            <RequireAuth>
              <RequirePlatformAdmin>
                <PlatformLayout />
              </RequirePlatformAdmin>
            </RequireAuth>
          }
        >
          <Route index element={<HealthPage />} />
          <Route path="organizations" element={<OrganizationsPage />} />
          <Route path="organizations/:orgId" element={<OrganizationPage />} />
          <Route path="interviews" element={<AllInterviewsPage />} />
          <Route path="interviews/:sessionId" element={<InterviewReportPage />} />
          <Route path="workers" element={<WorkersPage />} />
          <Route path="queues" element={<QueuesPage />} />
          <Route path="problems" element={<ProblemsPage />} />
          <Route path="problems/new" element={<ProblemEditorPage />} />
          <Route path="problems/:problemId" element={<ProblemEditorPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="demo" element={<DemoPage />} />
          <Route path="*" element={<NotFoundContent />} />
        </Route>

        {/* Old dashboard URLs (bookmarks, links in old messages) */}
        <Route path="/dashboard" element={<Home />} />
        <Route path="/dashboard/ops" element={<Home />} />
        <Route path="/dashboard/invites" element={<LegacyRedirect to="/app/invites" />} />
        <Route path="/dashboard/roles" element={<LegacyRedirect to="/app/roles" />} />
        <Route path="/dashboard/rankings" element={<LegacyRedirect to="/app/rankings" />} />
        <Route path="/dashboard/team" element={<LegacyRedirect to="/app/team" />} />
        <Route path="/dashboard/session/:sessionId" element={<OldSessionRedirect />} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthProvider>
  );
}
