/**
 * Type definitions for the study buddy web app.
 */

export interface CallResponse {
  call_id: string;
  session_id: string;
  room_name: string;
  livekit_url: string;
  livekit_token: string;
  status: string;
}

/** Starting language; the learner can switch by speaking another one. */
export type BuddyLanguage = 'ml-IN' | 'te-IN' | 'en-IN';

/** Study (teach + gentle checks) or just talk (a warm listener). */
export type SessionMode = 'study' | 'talk';

export interface CreateCallRequest {
  candidate_name: string;
  language: BuddyLanguage;
  mode: SessionMode;
}

export interface CallStatus {
  call_id: string;
  session_id: string;
  status: string;
  participant_count: number;
  created_at?: string;
}

export type InterviewState = 'idle' | 'connecting' | 'connected' | 'error' | 'ended';

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  role: 'admin' | 'recruiter';
  org_id: string;
  org_name?: string;
  is_platform_admin: boolean;
}
