/**
 * API service for communicating with the Avatar Service backend.
 */

import type { CallResponse, CreateCallRequest } from '../types';

const API_BASE = '/api';

/**
 * Start a study session (creates the LiveKit room).
 * Returns LiveKit connection details.
 */
export async function createCall(request: CreateCallRequest): Promise<CallResponse> {
  const response = await fetch(`${API_BASE}/calls/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to create call: ${response.status}`);
  }

  return response.json();
}

export type ReadPage = { page_id: string; topic: string; points: string[]; summary: string };

/** Read a photographed textbook page (data URL); the buddy then teaches from it. */
export async function readPage(image: string, language: string): Promise<ReadPage> {
  const response = await fetch(`${API_BASE}/pages/read`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image, language }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '' }));
    throw new Error(typeof error.detail === 'string' && error.detail ? error.detail : `Couldn't read the page (${response.status})`);
  }
  return response.json();
}

/**
 * End an active call.
 */
export async function endCall(callId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/calls/${callId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    console.warn('Failed to end call:', response.status);
  }
}

/**
 * Get call status.
 */
export async function getCallStatus(callId: string): Promise<{
  call_id: string;
  session_id: string;
  status: string;
  participant_count: number;
}> {
  const response = await fetch(`${API_BASE}/calls/${callId}`);

  if (!response.ok) {
    throw new Error(`Failed to get call status: ${response.status}`);
  }

  return response.json();
}

export interface Progress {
  topic: string | null;
  language: string | null;
  ideas: { text: string; status: 'unseen' | 'partial' | 'gap' | 'understood' }[];
  covered: number;
}

/**
 * What the learner has covered: topic + key ideas (from the brain's understanding map).
 */
export async function getProgress(callId: string): Promise<Progress> {
  const response = await fetch(`${API_BASE}/calls/${callId}/progress`);
  if (!response.ok) throw new Error(`Failed to get progress: ${response.status}`);
  return response.json();
}

export interface Recap {
  title: string;
  summary: string;
  covered: string[];
  improved: string[];
  next_time: string;
  language?: string;
  mode?: 'study' | 'talk';
  /** Helpline text, shown when self-harm came up in the session */
  help?: string;
}

/** The end-of-session recap card ("pending" while the buddy is still writing it). */
export async function getRecap(sessionId: string): Promise<{ status: 'pending' | 'ready' | 'failed'; recap: Recap | null }> {
  const response = await fetch(`${API_BASE}/calls/recap/${encodeURIComponent(sessionId)}`);
  if (!response.ok) throw new Error(`Failed to get recap: ${response.status}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// The learner's own sessions and progress (/me)
// ---------------------------------------------------------------------------

export interface SessionSummary {
  session_id: string;
  created_at: string | null;
  ended_at: string | null;
  status: string;
  mode: 'study' | 'talk';
  language: string | null;
  topic: string | null;
  title: string | null;
  summary: string | null;
  next_time: string | null;
  ideas_total: number;
  ideas_understood: number;
  level: Level | null;
  mood: Mood | null;
  self_mood: string | null;
}

export type Level = 'just_started' | 'getting_there' | 'confident';
export type MoodLabel = 'calm' | 'happy' | 'tired' | 'bored' | 'stressed' | 'anxious' | 'frustrated' | 'sad';
export interface Mood {
  level: number;
  label: MoodLabel;
}

export interface Suggestions {
  continue: { topic: string; level: Level | null; next_concept: string | null; ideas_understood: number; ideas_total: number }[];
  next_topics: string[];
}

export interface SessionDetail extends SessionSummary {
  recap: Recap | null;
  ideas: { text: string; status: 'unseen' | 'partial' | 'gap' | 'understood' }[];
}

export interface Stats {
  streak_days: number;
  sessions_total: number;
  sessions_this_week: number;
  ideas_understood: number;
  topics: {
    topic: string;
    sessions: number;
    ideas_understood: number;
    ideas_total: number;
    last: string | null;
    level: Level | null;
  }[];
  last_14_days: { day: string; active: boolean; mood_level: number | null; mood_label: MoodLabel | null }[];
  mood: { average: number; trend: 'up' | 'down' | 'steady'; common_label: MoodLabel | null; days_with_mood: number } | null;
  crisis_recent: boolean;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const err = new Error(`Request failed: ${response.status}`) as Error & { status?: number };
    err.status = response.status;
    throw err;
  }
  return response.json();
}

// `lang`: saved text comes back in this language (translated if needed)
export const getMySessions = (lang: string) => getJson<{ sessions: SessionSummary[] }>(`/me/sessions?lang=${lang}`);
export const getMySession = (id: string, lang: string) =>
  getJson<SessionDetail>(`/me/sessions/${encodeURIComponent(id)}?lang=${lang}`);
export const getMyStats = (lang: string) => getJson<Stats>(`/me/stats?lang=${lang}`);
export const getMySuggestions = (lang: string) => getJson<Suggestions>(`/me/suggestions?lang=${lang}`);

/**
 * Health check for the API.
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
