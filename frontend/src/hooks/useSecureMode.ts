/**
 * useSecureMode - Locks the desktop app for the length of an interview and
 * sends its proctoring events to the recruiter's session.
 */

import { useEffect, useRef } from 'react';
import { reportCheatFlag } from '@/services/proctoringApi';
import { getDesktop, type DesktopViolation } from '@/services/desktopApp';
import type { InterviewState } from '@/types';

interface UseSecureModeOptions {
  state: InterviewState;
  sessionId: string | null;
  inviteToken: string | null;
  /** The invite can't be used, so there is no interview to stay locked for */
  inviteDead: boolean;
  /** The candidate chose to continue in a browser, without the lock */
  browserMode: boolean;
}

export function useSecureMode({ state, sessionId, inviteToken, inviteDead, browserMode }: UseSecureModeOptions) {
  const sessionRef = useRef<string | null>(null);
  const queueRef = useRef<DesktopViolation[]>([]);
  const browserReportedRef = useRef(false);

  const send = (violation: DesktopViolation) => {
    const session = sessionRef.current;
    if (!session) {
      queueRef.current.push(violation);
      return;
    }
    reportCheatFlag({ session_id: session, confidence: 1, ...violation }).catch((err) => {
      console.error('Could not report proctoring event:', err);
    });
  };

  // Lock on start, unlock only when the interview is over
  useEffect(() => {
    const desktop = getDesktop();
    if (!desktop || !inviteToken) return;
    if (state === 'connecting' || state === 'connected') void desktop.lock(inviteToken);
    if (state === 'ended' || state === 'error' || inviteDead) void desktop.unlock();
  }, [state, inviteToken, inviteDead]);

  // Events can arrive before there is a session to file them under
  useEffect(() => {
    const desktop = getDesktop();
    if (!desktop) return;
    return desktop.onViolation(send);
  }, []);

  useEffect(() => {
    sessionRef.current = sessionId;
    if (!sessionId) return;
    queueRef.current.splice(0).forEach(send);
    if (browserMode && !browserReportedRef.current) {
      browserReportedRef.current = true;
      send({
        flag_type: 'browser_mode',
        severity: 'medium',
        description: 'The candidate took this interview in a browser, without the locked app',
      });
    }
  }, [sessionId, browserMode]);
}
