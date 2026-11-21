/**
 * Routes.
 *   /        sends you to /study, or to /login when signed out
 *   /study   the study session (signed-in learners)
 *   /login   sign-in / sign-up
 */

import { Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, RequireAuth } from './hooks/useAuth';
import { StudyPage } from './features/study/StudyPage';
import { LoginPage } from './pages/LoginPage';
import { Home, NotFound } from './areas/shared/routing';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/study"
          element={
            <RequireAuth>
              <StudyPage />
            </RequireAuth>
          }
        />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </AuthProvider>
  );
}
