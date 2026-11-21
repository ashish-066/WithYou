/**
 * Study session call state: start (create the LiveKit room) and end.
 */

import { useState, useCallback } from 'react';
import type { BuddyLanguage, CallResponse, InterviewState } from '../types';
import { createCall, endCall } from '../services/api';

interface UseInterviewCallReturn {
  state: InterviewState;
  callData: CallResponse | null;
  error: string | null;
  startCall: (learnerName: string, language: BuddyLanguage) => Promise<void>;
  endCurrentCall: () => Promise<void>;
}

export function useInterviewCall(): UseInterviewCallReturn {
  const [state, setState] = useState<InterviewState>('idle');
  const [callData, setCallData] = useState<CallResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startCall = useCallback(async (learnerName: string, language: BuddyLanguage) => {
    setState('connecting');
    setError(null);
    try {
      const response = await createCall({ candidate_name: learnerName, language });
      setCallData(response);
      setState('connected');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start the session');
      setState('error');
    }
  }, []);

  const endCurrentCall = useCallback(async () => {
    if (callData) {
      try {
        await endCall(callData.call_id);
      } catch (err) {
        console.warn('Error ending call:', err);
      }
    }
    setCallData(null);
    setState('ended');
  }, [callData]);

  return { state, callData, error, startCall, endCurrentCall };
}
