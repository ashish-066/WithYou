/**
 * Custom hook for managing interview call state.
 */

import { useState, useCallback } from 'react';
import type { CallResponse, InterviewState } from '../types';
import { createCall, endCall } from '../services/api';

interface StartCallParams {
  inviteToken?: string;
  candidateName: string;
  roleId?: string;
  githubUrl?: string;
  linkedinUrl?: string;
  resumeText?: string;
  interviewMode?: 'round1' | 'round2_dsa';
  dsaProblemId?: string;
}

interface UseInterviewCallReturn {
  state: InterviewState;
  callData: CallResponse | null;
  error: string | null;
  interviewMode: 'round1' | 'round2_dsa';
  dsaProblemId: string | null;
  startCall: (params: StartCallParams) => Promise<void>;
  endCurrentCall: () => Promise<void>;
}

export function useInterviewCall(): UseInterviewCallReturn {
  const [state, setState] = useState<InterviewState>('idle');
  const [callData, setCallData] = useState<CallResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [interviewMode, setInterviewMode] = useState<'round1' | 'round2_dsa'>('round1');
  const [dsaProblemId, setDsaProblemId] = useState<string | null>(null);

  const startCall = useCallback(async ({ 
    inviteToken,
    candidateName, 
    roleId,
    githubUrl, 
    linkedinUrl, 
    resumeText,
    interviewMode = 'round1',
    dsaProblemId,
  }: StartCallParams) => {
    setState('connecting');
    setError(null);
    setInterviewMode(interviewMode);
    setDsaProblemId(dsaProblemId ?? null);

    try {
      const response = await createCall({
        invite_token: inviteToken,
        candidate_name: candidateName,
        role_id: roleId,
        github_url: githubUrl,
        linkedin_url: linkedinUrl,
        resume_text: resumeText,
        interview_mode: interviewMode,
        dsa_problem_id: dsaProblemId,
      });

      setCallData(response);
      setState('connected');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start call';
      setError(message);
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

  return {
    state,
    callData,
    error,
    interviewMode,
    dsaProblemId,
    startCall,
    endCurrentCall,
  };
}
