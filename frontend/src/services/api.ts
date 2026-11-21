/**
 * API service for communicating with the Avatar Service backend.
 */

import type { CallResponse, CreateCallRequest } from '../types';

const API_BASE = '/api';

/**
 * Create a new interview call.
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

/**
 * Upload a resume file for OCR processing.
 */
export async function uploadResume(
  file: File,
  inviteToken?: string,
): Promise<{ resume_text: string; filename: string }> {
  const formData = new FormData();
  formData.append('file', file);
  // Before the call starts, the candidate's invite authorizes the upload
  if (inviteToken) formData.append('invite_token', inviteToken);

  const response = await fetch(`${API_BASE}/resumes/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to upload resume: ${response.status}`);
  }

  return response.json();
}

/**
 * Health check for the API.
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
