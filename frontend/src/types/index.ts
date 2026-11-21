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

export interface CreateCallRequest {
  candidate_name: string;
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
