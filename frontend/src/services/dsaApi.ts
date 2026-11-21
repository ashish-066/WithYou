/**
 * DSA API service — communicates with the backend DSA problem endpoints.
 */

import type { DSAProblemMeta, DSAProblemPublic } from '../types';

const API_BASE = '/api';

/**
 * List all DSA problems (admin metadata view).
 */
export async function listDSAProblems(): Promise<DSAProblemMeta[]> {
  const res = await fetch(`${API_BASE}/admin/dsa/problems/`);
  if (!res.ok) throw new Error(`Failed to list DSA problems: ${res.status}`);
  return res.json();
}

/**
 * Get candidate-safe problem view (no reference solution, no hidden tests).
 */
export async function getDSAProblemPublic(problemId: string): Promise<DSAProblemPublic> {
  const res = await fetch(`${API_BASE}/admin/dsa/problems/${problemId}/public`);
  if (!res.ok) throw new Error(`Problem '${problemId}' not found`);
  return res.json();
}

/**
 * Submit candidate code for execution against public test cases.
 * The backend runs the code in a sandboxed subprocess (Python only).
 *
 * This is sent via the Redis stream mechanism (not a direct REST call)
 * so the response comes back through the LiveKit agent.
 *
 * This REST call posts to the avatar service which publishes a
 * dsa_code_execute message to the interview:requests stream.
 */
export async function submitCode(
  sessionId: string,
  code: string,
  _language: string = 'python',
): Promise<{ queued: boolean }> {
  const res = await fetch(`${API_BASE}/calls/dsa/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, code, language: _language }),
  });
  if (!res.ok) throw new Error(`Failed to submit code: ${res.status}`);
  return res.json();
}
