/**
 * Study session call state: start (create the LiveKit room) and end.
 */

import { useState, useCallback } from 'react';
import type { BuddyLanguage, CallResponse, InterviewState, SessionMode } from '../types';
import { createCall, endCall } from '../services/api';

interface UseInterviewCallReturn {
  state: InterviewState;
  callData: CallResponse | null;
  error: string | null;
  /** The session that just ended (its recap is shown on the finish screen) */
  endedSessionId: string | null;
  startCall: (
    learnerName: string,
    language: BuddyLanguage,
    mode: SessionMode,
    topic?: string,
    voice?: 'kavya' | 'shubh',
    pageId?: string,
  ) => Promise<void>;
  endCurrentCall: () => Promise<void>;
}

export function useInterviewCall(): UseInterviewCallReturn {
  const [state, setState] = useState<InterviewState>('idle');
  const [callData, setCallData] = useState<CallResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [endedSessionId, setEndedSessionId] = useState<string | null>(null);

  const startCall = useCallback(
    async (learnerName: string, language: BuddyLanguage, mode: SessionMode, topic?: string, voice?: 'kavya' | 'shubh', pageId?: string) => {
    setState('connecting');
    setError(null);
    try {
      const response = await createCall({ candidate_name: learnerName, language, mode, topic, voice, page_id: pageId });
      setCallData(response);
      setState('connected');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start the session');
      setState('error');
    }
  },
    [],
  );

  const endCurrentCall = useCallback(async () => {
    if (callData) {
      try {
        await endCall(callData.call_id);
      } catch (err) {
        console.warn('Error ending call:', err);
      }
    }
    setEndedSessionId(callData?.session_id ?? null);
    setCallData(null);
    setState('ended');
  }, [callData]);

  return { state, callData, error, endedSessionId, startCall, endCurrentCall };
}
