/**
 * Routes.
 *   /             Home (signed in), /learn topic picker, /history (+ /:id),
 *   /progress, /me: inside the app frame (tab bar / side rail)
 *   /session      a live study or talk session, full screen
 *   /login        sign-in / sign-up
 */

import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, RequireAuth } from './hooks/useAuth';
import { LoginPage } from './pages/LoginPage';
import { NotFound } from './areas/shared/routing';
import { AppShell } from './features/app/AppShell';
import { HomePage } from './features/app/HomePage';
import { LearnPage } from './features/app/LearnPage';
import { HistoryPage, SessionDetailPage } from './features/app/HistoryPages';
import { ProfilePage, ProgressPage } from './features/app/ProgressProfile';
import { StudyPage } from './features/study/StudyPage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/session"
          element={
            <RequireAuth>
              <StudyPage />
            </RequireAuth>
          }
        />
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="learn" element={<LearnPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="history/:id" element={<SessionDetailPage />} />
          <Route path="progress" element={<ProgressPage />} />
          <Route path="me" element={<ProfilePage />} />
        </Route>
        {/* Old links */}
        <Route path="/study" element={<Navigate to="/" replace />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthProvider>
  );
}
