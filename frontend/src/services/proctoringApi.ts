/**
 * Proctoring API client for anti-cheating functionality.
 */

import type { CheatFlagType, SeverityLevel, IntegrityReport } from '@/types';

const API_BASE = '/api/proctoring';

// =============================================================================
// Request/Response Types
// =============================================================================

export interface CheatFlagRequest {
  session_id: string;
  flag_type: CheatFlagType;
  severity: SeverityLevel;
  confidence: number;
  description: string;
  evidence?: string;
  client_timestamp?: string;
}

export interface CheatFlagResponse {
  flag_id: string;
  session_id: string;
  flag_type: CheatFlagType;
  severity: SeverityLevel;
  recorded_at: string;
  integrity_score: number;
}

export interface IntegrityStatusResponse {
  session_id: string;
  integrity_score: number;
  total_flags: number;
  flags_by_type: Record<string, number>;
  flags_by_severity: Record<string, number>;
  recommendation: 'proceed' | 'review' | 'flag' | 'reject';
}

export interface IntegrityReportResponse extends IntegrityReport {
  session_id: string;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Report a single cheat flag detected during the interview.
 */
export async function reportCheatFlag(request: CheatFlagRequest): Promise<CheatFlagResponse> {
  const response = await fetch(`${API_BASE}/flags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...request,
      client_timestamp: request.client_timestamp || new Date().toISOString(),
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to report cheat flag: ${response.status}`);
  }

  return response.json();
}

/**
 * Report multiple cheat flags in a single request.
 */
export async function reportCheatFlagsBatch(
  sessionId: string,
  flags: Omit<CheatFlagRequest, 'session_id'>[]
): Promise<{
  session_id: string;
  flags_recorded: number;
  flag_ids: string[];
  integrity_score: number;
}> {
  const response = await fetch(`${API_BASE}/flags/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      flags: flags.map((flag) => ({
        ...flag,
        session_id: sessionId,
        client_timestamp: flag.client_timestamp || new Date().toISOString(),
      })),
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to report cheat flags: ${response.status}`);
  }

  return response.json();
}

/**
 * Get current integrity status for a session.
 */
export async function getIntegrityStatus(sessionId: string): Promise<IntegrityStatusResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/status`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch integrity status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get full integrity report for a session.
 */
export async function getIntegrityReport(sessionId: string): Promise<IntegrityReportResponse> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/report`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch integrity report: ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// Convenience Functions for Common Flag Types
// =============================================================================

/**
 * Report multiple faces detected in camera.
 */
export function reportMultipleFaces(
  sessionId: string,
  confidence: number,
  evidence?: string
): Promise<CheatFlagResponse> {
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'multiple_faces',
    severity: confidence > 0.8 ? 'high' : 'medium',
    confidence,
    description: 'Multiple faces detected in camera view',
    evidence,
  });
}

/**
 * Report no face detected in camera.
 */
export function reportNoFace(
  sessionId: string,
  confidence: number,
  evidence?: string
): Promise<CheatFlagResponse> {
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'no_face',
    severity: 'low',
    confidence,
    description: 'Candidate face not visible in camera',
    evidence,
  });
}

/**
 * Report phone detected in camera view.
 */
export function reportPhoneDetected(
  sessionId: string,
  confidence: number,
  evidence?: string
): Promise<CheatFlagResponse> {
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'phone_detected',
    severity: confidence > 0.8 ? 'high' : 'medium',
    confidence,
    description: 'Mobile phone visible in camera view',
    evidence,
  });
}

/**
 * Report earphone/earbud detected.
 */
export function reportEarphoneDetected(
  sessionId: string,
  confidence: number,
  evidence?: string
): Promise<CheatFlagResponse> {
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'earphone_detected',
    severity: 'medium',
    confidence,
    description: 'Earphone or earbud detected',
    evidence,
  });
}

/**
 * Report browser tab switch.
 */
export function reportTabSwitch(
  sessionId: string,
  duration?: number
): Promise<CheatFlagResponse> {
  const severity = duration && duration > 10000 ? 'high' : 'medium';
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'tab_switch',
    severity,
    confidence: 1.0,
    description: `Browser tab switched${duration ? ` for ${Math.round(duration / 1000)}s` : ''}`,
    evidence: duration ? `Duration: ${duration}ms` : undefined,
  });
}

/**
 * Report suspected AI assistance in response.
 */
export function reportAIAssistance(
  sessionId: string,
  confidence: number,
  responseText?: string
): Promise<CheatFlagResponse> {
  return reportCheatFlag({
    session_id: sessionId,
    flag_type: 'ai_assistance',
    severity: confidence > 0.8 ? 'critical' : 'high',
    confidence,
    description: 'Response pattern suggests AI-generated content',
    evidence: responseText?.substring(0, 200),
  });
}
