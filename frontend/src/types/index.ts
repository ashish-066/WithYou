/**
 * Type definitions for the Presence View Interview application.
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
  /** Candidate invite link token; the invite decides role, round and problem */
  invite_token?: string;
  candidate_name: string;
  role_id?: string;
  github_url?: string;
  linkedin_url?: string;
  resume_url?: string;
  resume_text?: string;
  /** 'round1' (default) or 'round2_dsa' */
  interview_mode?: 'round1' | 'round2_dsa';
  /** Required when interview_mode = 'round2_dsa' */
  dsa_problem_id?: string;
}

export interface ResumeUploadResponse {
  resume_text: string;
  filename: string;
}

export interface CallStatus {
  call_id: string;
  session_id: string;
  status: string;
  participant_count: number;
  created_at?: string;
}

export type InterviewState = 'idle' | 'connecting' | 'connected' | 'error' | 'ended';

// =============================================================================
// Dashboard Types
// =============================================================================

export interface SessionSummary {
  session_id: string;
  candidate_id?: string;
  turn_count: number;
  max_turns: number;
  brain_mode: 'fast' | 'slow' | 'idle';
  interview_ended: boolean;
  trust_score: number;
  started_at?: string;
  last_updated?: string;
}

export interface Message {
  role: 'system' | 'assistant' | 'user';
  content: string;
  timestamp: string;
}

// SSE Event Types

// =============================================================================
// Skill Tree Scoring Types (Evidence-Based Assessment)
// =============================================================================

// =============================================================================
// Job Role Management Types
// =============================================================================

export interface JobRole {
  role_id: string;
  role_title: string;
  job_description: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface JobRoleCreate {
  role_id: string;
  role_title: string;
  job_description: string;
  is_active?: boolean;
}

export interface JobRoleUpdate {
  role_title?: string;
  job_description?: string;
  is_active?: boolean;
}

export interface JobRoleListResponse {
  total_roles: number;
  roles: JobRole[];
}

// =============================================================================
// Anti-Cheating / Proctoring Types
// =============================================================================

export type CheatFlagType =
  | 'multiple_faces'
  | 'no_face'
  | 'phone_detected'
  | 'earphone_detected'
  | 'tab_switch'
  | 'screen_share'
  | 'voice_change'
  | 'copy_paste'
  | 'ai_assistance'
  | 'suspicious_timing'
  | 'blocked_app'
  | 'second_screen'
  | 'app_closed'
  | 'exit_attempt'
  | 'emergency_exit'
  | 'lock_expired'
  | 'browser_mode';

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical';

export interface CheatFlag {
  id: string;
  flag_type: CheatFlagType;
  severity: SeverityLevel;
  confidence: number;
  description: string;
  evidence?: string;
  timestamp: string;
  turn_number: number;
}

export interface IntegrityReport {
  integrity_score: number;
  total_flags: number;
  flags_by_type: Record<string, number>;
  flags_by_severity: Record<string, number>;
  critical_incidents: CheatFlag[];
  timeline: CheatFlag[];
  recommendation: 'proceed' | 'review' | 'flag' | 'reject';
  summary: string;
}

// =============================================================================
// DSA Round 2 Types
// =============================================================================

export type DSADifficulty = 'easy' | 'medium' | 'hard';

export interface DSATestCase {
  input: string;
  expected_output: string;
  is_hidden: boolean;
  description: string;
}

/** Candidate-safe problem view (no reference solution, no hidden tests) */
export interface DSAProblemPublic {
  problem_id: string;
  title: string;
  statement: string;
  constraints: string[];
  difficulty: DSADifficulty;
  tags: string[];
  public_test_cases: DSATestCase[];
}

/** Metadata row returned by list endpoint */
export interface DSAProblemMeta {
  problem_id: string;
  title: string;
  difficulty: DSADifficulty;
  tags: string[];
  created_at: string;
  created_by: string;
}

export interface DSATestCaseResult {
  test_index: number;
  description: string;
  passed: boolean;
  input: string;
  expected_output: string;
  actual_output: string;
  error: string;
  runtime_ms: number;
}

export interface DSAExecutionResult {
  success: boolean;
  compilation_error: string;
  runtime_error: string;
  timed_out: boolean;
  timeout_seconds: number;
  test_results: DSATestCaseResult[];
  tests_passed: number;
  tests_total: number;
  pass_rate: number;
  total_runtime_ms: number;
  code_version: number;
  executed_at: string;
}

export interface DSARubricScores {
  problem_understanding?: number;
  algorithm_selection?: number;
  reasoning?: number;
  code_correctness?: number;
  complexity_analysis?: number;
  edge_case_handling?: number;
  optimization?: number;
  communication?: number;
}

export interface DSAInterviewStatePublic {
  problem_id: string;
  problem_title: string;
  difficulty: DSADifficulty;
  current_approach: string | null;
  current_code: string | null;
  code_language: string;
  last_execution_result: DSAExecutionResult | null;
  hints_used: number;
  dsa_turn_count: number;
  scores: DSARubricScores;
}

// =============================================================================
// Auth
// =============================================================================

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  role: 'admin' | 'recruiter';
  org_id: string;
  org_name?: string;
  is_platform_admin: boolean;
}

export type InterviewMode = 'round1' | 'round2_dsa';

export interface CreateInviteRequest {
  candidate_name: string;
  candidate_email?: string;
  role_id?: string;
  interview_mode: InterviewMode;
  dsa_problem_id?: string;
  require_secure_app?: boolean;
  expires_in_hours?: number;
  /** Candidate background: the interviewer asks about it and checks claims against it */
  github_url?: string;
  linkedin_url?: string;
  other_links?: string[];
  resume_text?: string;
  linkedin_text?: string;
}

export interface InviteBackground {
  github_url: string;
  linkedin_url: string;
  other_links: string[];
  has_resume: boolean;
  has_linkedin_export: boolean;
}

export interface CreatedInvite {
  invite_id: string;
  token: string;
  /** e.g. /interview?invite=... (prefix with the site origin to share) */
  path: string;
  expires_at: string;
}

export interface CandidateInvite {
  invite_id: string;
  candidate_name: string;
  candidate_email: string;
  role_id: string;
  role_title: string;
  interview_mode: InterviewMode;
  dsa_problem_id: string;
  require_secure_app: boolean;
  created_at: string;
  expires_at: string;
  status: 'pending' | 'used' | 'expired' | 'revoked';
  session_id: string;
  background?: InviteBackground;
}

/** What a candidate's setup screen learns from their invite link */
export interface InviteInfo {
  candidate_name: string;
  role_title: string;
  interview_mode: InterviewMode;
  dsa_problem_id: string;
  require_secure_app: boolean;
  expires_at: string;
  status: 'pending' | 'used' | 'expired' | 'revoked';
}

/** One interview in the organization workspace (GET /org/interviews) */
export interface OrgInterview {
  session_id: string;
  candidate_name: string;
  candidate_email: string;
  role_id: string;
  role_title: string;
  interview_mode: InterviewMode;
  status: 'in_progress' | 'completed';
  end_reason: string;
  created_at: string | null;
  ended_at: string | null;
  last_activity: string | null;
  turn_count: number;
  max_turns: number;
  integrity_score: number | null;
  has_report: boolean;
}

// =============================================================================
// Interview report (GET /org/interviews/{id})
// =============================================================================

export type HiringDecision = 'advance' | 'hold' | 'reject';

export interface InterviewDecision {
  decision: HiringDecision;
  note: string;
  decided_at: string | null;
  decided_by: { user_id: string; name: string; email: string } | null;
}

export interface TranscriptEntry {
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  timestamp?: string;
  turn?: number | null;
}

export interface WrittenReport {
  summary?: string;
  strengths?: string[];
  concerns?: string[];
  recommendation?: 'strong_yes' | 'yes' | 'maybe' | 'no' | 'strong_no' | string;
  detailed_sections?: Record<string, unknown>;
}

/** Proof for a camera-check flag (raised by the voice agent on our server) */
export interface FlagEvidence {
  photo_key?: string;
  sha256?: string;
  frame_size?: [number, number];
  model?: string;
  /** Seconds into the recording */
  recording_seconds?: number;
  detections?: Array<{ label: string; score: number; box: [number, number, number, number] }>;
}

/**
 * An answer that came after a long silence, and the follow-up question asked
 * to test whether the candidate understood it (worker: brain/verification_probe.py)
 */
export interface VerificationProbe {
  flag_id?: string;
  turn?: number;
  latency_ms: number;
  words: number;
  answer: string;
  question?: string;
  probe_answer?: string;
  probe_latency_ms?: number | null;
  probe_words?: number;
  outcome: 'asked' | 'answered' | 'passed' | 'failed' | 'unanswered' | 'inconclusive' | string;
  reason?: string;
}

export interface CheatFlagEntry {
  id?: string;
  flag_id?: string;
  flag_type: string;
  /** Camera checks: structured proof. Older browser flags: free text */
  evidence?: FlagEvidence | string | null;
  source?: string;
  severity?: 'low' | 'medium' | 'high' | 'critical' | string;
  confidence?: number;
  description?: string;
  timestamp?: string;
  turn_number?: number;
}

export interface TimestampNoteEntry {
  tag?: string;
  content?: string;
  turn_number?: number;
  video_seconds?: number;
}

export interface IntegrityReportData {
  integrity_score?: number;
  recommendation?: 'proceed' | 'review' | 'flag' | 'reject' | string;
  summary?: string;
  critical_incidents?: unknown[];
}

export interface CodeVersion {
  version: number;
  code: string;
  language?: string;
  timestamp?: string;
  execution_result?: { tests_passed?: number; tests_total?: number; pass_rate?: number } & Record<string, unknown>;
}

export interface InterviewDetail {
  session_id: string;
  org_id: string | null;
  candidate_name: string;
  candidate_email: string;
  role_id: string;
  role_title: string;
  interview_mode: InterviewMode;
  status: 'in_progress' | 'completed';
  live: boolean;
  end_reason: string;
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  last_activity: string | null;
  turn_count: number;
  max_turns: number;
  /** failed: the worker couldn't write it (or it's long overdue); it can be retried */
  report_status: 'ready' | 'pending' | 'failed' | 'not_started';
  report: WrittenReport | null;
  /** Technical round: rubric scores etc. Coding round: the DSA final report. */
  analytics: Record<string, any> | null;
  skill_tree: {
    skill_weights?: Record<string, number>;
    current_levels?: Record<string, number>;
    evidence_counts?: Record<string, number>;
    score_percentage?: number;
    elo_rating?: number;
  } | null;
  dsa_state: { code_versions?: CodeVersion[]; current_code?: string } & Record<string, any> | null;
  scores: {
    running_scores: Record<string, number> | null;
    trust_score: number | null;
    integrity_score: number | null;
    verified_claims: unknown[] | null;
  };
  integrity: {
    integrity_score: number | null;
    cheat_flags: CheatFlagEntry[];
    integrity_report: IntegrityReportData | null;
    timestamp_notes: TimestampNoteEntry[];
    /** Time from the end of each question to the candidate's first word */
    response_timings: Array<{ turn: number; latency_ms: number; words: number }>;
    /** Follow-ups asked to test answers that looked looked-up */
    verification_probes?: VerificationProbe[];
  };
  /** How the interview went (end reason, length, unanswered, absences) */
  completion: {
    end_reason: string | null;
    incomplete: boolean;
    minutes: number | null;
    wrap_up_reason: string | null;
    unanswered_questions: number;
    absences: number;
    skills_not_assessed: string[];
    median_response_ms: number | null;
  } | null;
  transcript: { messages: TranscriptEntry[]; summary: unknown };
  recording: { status: string; url: string | null };
  decision: InterviewDecision | null;
  can_decide: boolean;
  /** Platform admins only: the raw live state */
  internals?: Record<string, unknown> | null;
}

// =============================================================================
// Platform console (/platform/*)
// =============================================================================

export type HealthState = 'ok' | 'warn' | 'down';

export interface PlatformHealth {
  state: HealthState;
  checked_at: string;
  parts: Array<{ part: string; state: HealthState; detail: string }>;
}

export interface PlatformOrganization {
  org_id: string;
  name: string;
  members: number;
  interviews: number;
  last_active: string | null;
  created_at: string | null;
}

export interface PlatformInterview {
  session_id: string;
  org_id: string | null;
  org_name: string;
  candidate_name: string;
  candidate_email: string;
  role_id: string;
  role_title: string;
  interview_mode: InterviewMode;
  status: 'in_progress' | 'completed';
  end_reason: string;
  created_at: string | null;
  ended_at: string | null;
  last_activity: string | null;
  turn_count: number;
  integrity_score: number | null;
  has_report: boolean;
  decision: HiringDecision | null;
}

export interface PlatformOrganizationDetail {
  org_id: string;
  name: string;
  created_at: string | null;
  members_count: number;
  interviews_count: number;
  last_active: string | null;
  members: Array<{
    user_id: string;
    name: string;
    email: string;
    role: 'admin' | 'recruiter';
    is_platform_admin: boolean;
    created_at: string | null;
  }>;
  recent_interviews: PlatformInterview[];
}

export interface PlatformWorker {
  worker_id: string;
  hostname: string;
  status: string;
  stale: boolean;
  current_session: string | null;
  started_at: string | null;
  last_heartbeat: string | null;
  messages_processed: number;
  messages_failed: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
}

export interface PlatformStream {
  name: string;
  kind: 'requests' | 'responses';
  length: number;
  first_entry_id: string | null;
  last_entry_id: string | null;
  consumer_groups: number;
  pending_messages: number;
}

export interface DeadLetter {
  id: string;
  [field: string]: string;
}

export interface PlatformQueues {
  streams: PlatformStream[];
  dead_letters_total: number;
  dead_letters: DeadLetter[];
}

export interface AuditEventRow {
  id: number;
  at: string | null;
  org_id: string | null;
  org_name: string;
  actor_type: string;
  actor_id: string | null;
  actor_name: string;
  actor_email: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditPage {
  events: AuditEventRow[];
  next_before_id: number | null;
  actions: string[];
}

export interface AuditFilters {
  org_id?: string;
  actor?: string;
  action?: string;
  since?: string;
  until?: string;
}

// Coding problem library (/platform/problems)

export interface ProblemTestCase {
  input: string;
  expected_output: string;
  is_hidden?: boolean;
  description?: string;
}

export interface CodingProblem {
  problem_id: string;
  title: string;
  statement: string;
  constraints: string[];
  difficulty: DSADifficulty;
  tags: string[];
  reference_solution: {
    algorithm: string;
    time_complexity: string;
    space_complexity: string;
    code: string;
    explanation: string;
  };
  acceptable_alternatives: Array<{ algorithm: string; time_complexity: string; space_complexity: string; description: string }>;
  suboptimal_valid: Array<{
    algorithm: string;
    time_complexity: string;
    space_complexity: string;
    optimality_gap: string;
    is_acceptable_for_passing: boolean;
  }>;
  expected_concepts: string[];
  important_edge_cases: string[];
  follow_up_questions: string[];
  optimization_prompts: string[];
  interview_objectives: string[];
  public_test_cases: ProblemTestCase[];
  hidden_test_cases: ProblemTestCase[];
  stress_test_cases?: ProblemTestCase[];
  hint_policy: { allowed: boolean; max_hints: number; progressive: boolean; hints: string[]; hint_score_penalty: number };
  scoring_rubric: { dimensions: Array<{ name: string; weight: number; description: string }> };
  created_at?: string;
  created_by?: string;
}

export interface ProblemRow extends DSAProblemMeta {
  public_tests: number;
  hidden_tests: number;
  hints: number;
  invites: number;
  interviews: number;
}

// Rankings (/elo/*)

export interface RankingEntry {
  candidate_id: string;
  session_id: string | null;
  rating: number;
  matches_played: number;
  wins: number;
  losses: number;
  ties: number;
  percentile: number | null;
  rank: number | null;
  last_updated: string | null;
}

export interface RoleRankings {
  role_id: string;
  role_title: string | null;
  rankings: RankingEntry[];
  total_candidates: number;
  min_candidates_required: number;
  rankings_available: boolean;
}

export interface CandidateComparison {
  candidate_a_id: string;
  candidate_b_id: string;
  candidate_a_rating: number;
  candidate_b_rating: number;
  skill_comparisons: Array<{ skill_name: string; level_a: number; level_b: number; weight: number; winner: 'a' | 'b' | 'tie' }>;
  total_a: number;
  total_b: number;
  overall_winner: 'a' | 'b' | 'tie';
}

// Scalability demo (/admin/demo/*)

export interface DemoRunStatus {
  running: boolean;
  sessions: Array<{
    session_id: string;
    candidate_name: string;
    status: string;
    turn_count: number;
    script_progress: number;
    elo_rating: number | null;
    elo_rank: number | null;
    score_percentage: number | null;
  }>;
  workers_spawned: number;
  started_at: string | null;
  completed_sessions: number;
  rankings_available: boolean;
}

export interface DemoRunConfig {
  session_count: number;
  max_workers: number;
  response_delay_ms: number;
  auto_spawn_workers: boolean;
}
