/**
 * Data for the new pages, on top of lib/api.ts and react-query.
 * One place per resource, so pages don't each fetch and cache on their own.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '@/lib/api';
import type {
  AuditFilters,
  AuditPage,
  AuthUser,
  CandidateComparison,
  CandidateInvite,
  CodingProblem,
  CreateInviteRequest,
  CreatedInvite,
  DSAProblemMeta,
  DemoRunConfig,
  DemoRunStatus,
  HiringDecision,
  InterviewDecision,
  InterviewDetail,
  JobRole,
  JobRoleCreate,
  JobRoleListResponse,
  JobRoleUpdate,
  OrgInterview,
  PlatformHealth,
  PlatformInterview,
  PlatformOrganization,
  PlatformOrganizationDetail,
  PlatformQueues,
  PlatformWorker,
  ProblemRow,
  RoleRankings,
  SessionSummary,
} from '@/types';

export const keys = {
  config: ['auth', 'config'] as const,
  sessions: (scope: 'org' | 'all') => ['sessions', scope] as const,
  orgInterviews: ['org', 'interviews'] as const,
  interview: (id: string) => ['org', 'interviews', id] as const,
  invites: ['invites'] as const,
  roles: ['roles'] as const,
  users: ['users'] as const,
  problems: ['dsa', 'problems'] as const,
  rankings: (roleId: string) => ['rankings', roleId] as const,
  compare: (roleId: string, a: string, b: string) => ['rankings', roleId, a, b] as const,
  demo: ['demo'] as const,
  platform: {
    health: ['platform', 'health'] as const,
    orgs: ['platform', 'organizations'] as const,
    org: (id: string) => ['platform', 'organizations', id] as const,
    interviews: (unowned: boolean) => ['platform', 'interviews', unowned] as const,
    workers: ['platform', 'workers'] as const,
    queues: ['platform', 'queues'] as const,
    audit: (f: AuditFilters) => ['platform', 'audit', f] as const,
    problems: ['platform', 'problems'] as const,
    problem: (id: string) => ['platform', 'problems', id] as const,
  },
};

export interface AuthConfig {
  signup_enabled: boolean;
  demo_enabled: boolean;
}

export function useAuthConfig() {
  return useQuery({
    queryKey: keys.config,
    queryFn: () => api.get<AuthConfig>('/auth/config', { allowUnauthenticated: true }),
    staleTime: 5 * 60_000,
  });
}

/** Sessions with live state in Redis. The workspace always asks for its own org only. */
export interface SessionRow extends SessionSummary {
  integrity_score?: number;
}

export function useSessions(scope: 'org' | 'all', live = true) {
  return useQuery({
    queryKey: keys.sessions(scope),
    queryFn: () =>
      api.get<{ sessions: SessionRow[] }>('/admin/sessions', { query: { own_org_only: scope === 'org' || undefined } }),
    select: (d) => d.sessions,
    // Only while the tab is visible (react-query pauses intervals in background tabs)
    refetchInterval: live ? 10_000 : false,
  });
}

export function useInvites() {
  return useQuery({
    queryKey: keys.invites,
    queryFn: () => api.get<{ invites: CandidateInvite[] }>('/auth/invites'),
    select: (d) => d.invites,
  });
}

export function useCreateInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateInviteRequest) => api.post<CreatedInvite>('/auth/invites', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invites }),
  });
}

export function useRoles() {
  return useQuery({
    queryKey: keys.roles,
    queryFn: () => api.get<JobRoleListResponse>('/admin/roles/', { query: { active_only: false } }),
    select: (d) => d.roles,
  });
}

export function useSaveRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { create: JobRoleCreate } | { id: string; update: JobRoleUpdate }) =>
      'create' in v
        ? api.post<JobRole>('/admin/roles/', v.create)
        : api.put<JobRole>(`/admin/roles/${encodeURIComponent(v.id)}`, v.update),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.roles }),
  });
}

export function useDeleteRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/admin/roles/${encodeURIComponent(id)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.roles }),
  });
}

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: keys.users,
    queryFn: () => api.get<{ users: AuthUser[] }>('/auth/users'),
    select: (d) => d.users,
    enabled,
  });
}

/** Adds a member; the server generates their one-time password and returns it once. */
export function useAddUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; email: string; role: 'admin' | 'recruiter' }) =>
      api.post<AuthUser & { one_time_password: string }>('/auth/users', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useChangeRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { userId: string; role: 'admin' | 'recruiter' }) =>
      api.patch<AuthUser>(`/org/users/${encodeURIComponent(v.userId)}`, { role: v.role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (userId: string) =>
      api.post<{ one_time_password: string }>(`/org/users/${encodeURIComponent(userId)}/reset-password`),
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.delete(`/org/users/${encodeURIComponent(userId)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.users }),
  });
}

/** The organization's interviews from Postgres, with live progress for running ones. */
export function useOrgInterviews() {
  return useQuery({
    queryKey: keys.orgInterviews,
    queryFn: () => api.get<{ interviews: OrgInterview[]; total: number; truncated: boolean }>('/org/interviews'),
    refetchInterval: 10_000,
  });
}

export function useRevokeInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) => api.post(`/org/invites/${encodeURIComponent(inviteId)}/revoke`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.invites }),
  });
}

/** A fresh link for a waiting invite (the original is shown only once). */
export function useInviteLink() {
  return useMutation({
    mutationFn: (inviteId: string) =>
      api.post<{ path: string; expires_at: string }>(`/org/invites/${encodeURIComponent(inviteId)}/link`),
  });
}

export function useDsaProblems(enabled = true) {
  return useQuery({
    queryKey: keys.problems,
    queryFn: () => api.get<DSAProblemMeta[]>('/admin/dsa/problems/'),
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** One interview for the report page. Running ones refresh every few seconds. */
export function useInterviewDetail(sessionId: string) {
  return useQuery({
    queryKey: keys.interview(sessionId),
    queryFn: () => api.get<InterviewDetail>(`/org/interviews/${encodeURIComponent(sessionId)}`),
    // Live: every few seconds; finished but report still being written: now and then
    refetchInterval: (q) =>
      q.state.data?.live ? 5_000 : q.state.data?.report_status === 'pending' ? 20_000 : false,
    // Not found / no access won't change on a retry
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  });
}

/** Write the report again for an ended interview that has none. */
export function useRetryReport(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/org/interviews/${encodeURIComponent(sessionId)}/report/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.interview(sessionId) }),
  });
}

export function useSetDecision(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { decision: HiringDecision | null; note: string }) =>
      api.put<{ session_id: string; decision: InterviewDecision | null }>(
        `/org/interviews/${encodeURIComponent(sessionId)}/decision`,
        body,
      ),
    onSuccess: (res) => {
      qc.setQueryData<InterviewDetail>(keys.interview(sessionId), (old) =>
        old ? { ...old, decision: res.decision } : old,
      );
    },
  });
}

// =============================================================================
// Platform console
// =============================================================================

export function usePlatformHealth() {
  return useQuery({
    queryKey: keys.platform.health,
    queryFn: () => api.get<PlatformHealth>('/platform/health'),
    refetchInterval: 10_000,
  });
}

export function usePlatformOrganizations() {
  return useQuery({
    queryKey: keys.platform.orgs,
    queryFn: () => api.get<{ organizations: PlatformOrganization[] }>('/platform/organizations'),
    select: (d) => d.organizations,
  });
}

export function usePlatformOrganization(orgId: string) {
  return useQuery({
    queryKey: keys.platform.org(orgId),
    queryFn: () => api.get<PlatformOrganizationDetail>(`/platform/organizations/${encodeURIComponent(orgId)}`),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  });
}

export function usePlatformInterviews(includeUnowned: boolean) {
  return useQuery({
    queryKey: keys.platform.interviews(includeUnowned),
    queryFn: () =>
      api.get<{ interviews: PlatformInterview[]; total: number; truncated: boolean }>('/platform/interviews', {
        query: { include_unowned: includeUnowned || undefined },
      }),
    refetchInterval: 15_000,
  });
}

export function usePlatformWorkers() {
  return useQuery({
    queryKey: keys.platform.workers,
    queryFn: () => api.get<{ workers: PlatformWorker[] }>('/platform/workers'),
    select: (d) => d.workers,
    refetchInterval: 5_000,
  });
}

export function usePlatformQueues() {
  return useQuery({
    queryKey: keys.platform.queues,
    queryFn: () => api.get<PlatformQueues>('/platform/queues'),
    refetchInterval: 5_000,
  });
}

/** Audit log, newest first; "load older" fetches the next page. */
export function useAuditLog(filters: AuditFilters) {
  return useInfiniteQuery({
    queryKey: keys.platform.audit(filters),
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) =>
      api.get<AuditPage>('/platform/audit', {
        query: {
          org_id: filters.org_id || undefined,
          actor: filters.actor || undefined,
          action: filters.action || undefined,
          // Dates from <input type="date">: the whole day, in the viewer's time zone
          since: filters.since ? new Date(`${filters.since}T00:00:00`).toISOString() : undefined,
          until: filters.until ? new Date(`${filters.until}T23:59:59.999`).toISOString() : undefined,
          before_id: pageParam,
          limit: 100,
        },
      }),
    getNextPageParam: (last) => last.next_before_id ?? undefined,
  });
}

// Coding problem library

export function usePlatformProblems() {
  return useQuery({
    queryKey: keys.platform.problems,
    queryFn: () => api.get<{ problems: ProblemRow[] }>('/platform/problems'),
    select: (d) => d.problems,
  });
}

export function usePlatformProblem(problemId: string | null) {
  return useQuery({
    queryKey: keys.platform.problem(problemId ?? ''),
    queryFn: () =>
      api.get<{ problem: CodingProblem; usage: { invites: number; interviews: number } }>(
        `/platform/problems/${encodeURIComponent(problemId ?? '')}`,
      ),
    enabled: !!problemId,
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  });
}

export function useSaveProblem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { create: boolean; problem: CodingProblem }) =>
      v.create
        ? api.post<{ problem: CodingProblem }>('/platform/problems', v.problem)
        : api.put<{ problem: CodingProblem }>(`/platform/problems/${encodeURIComponent(v.problem.problem_id)}`, v.problem),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.platform.problems, exact: true });
      qc.invalidateQueries({ queryKey: keys.problems });
      qc.setQueryData(keys.platform.problem(res.problem.problem_id), (old: { usage?: unknown } | undefined) => ({
        usage: old?.usage ?? { invites: 0, interviews: 0 },
        problem: res.problem,
      }));
    },
  });
}

export function useDeleteProblem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (problemId: string) => api.delete(`/platform/problems/${encodeURIComponent(problemId)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.platform.problems, exact: true });
      qc.invalidateQueries({ queryKey: keys.problems });
    },
  });
}

// =============================================================================
// Rankings
// =============================================================================

export function useRankings(roleId: string | null) {
  return useQuery({
    queryKey: keys.rankings(roleId ?? ''),
    queryFn: () => api.get<RoleRankings>(`/elo/rankings/${encodeURIComponent(roleId ?? '')}`),
    enabled: !!roleId,
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  });
}

export function useComparison(roleId: string | null, pair: [string, string] | null) {
  return useQuery({
    queryKey: keys.compare(roleId ?? '', pair?.[0] ?? '', pair?.[1] ?? ''),
    queryFn: () =>
      api.get<CandidateComparison>(
        `/elo/compare/${encodeURIComponent(roleId ?? '')}/${encodeURIComponent(pair![0])}/${encodeURIComponent(pair![1])}`,
      ),
    enabled: !!roleId && !!pair,
  });
}

// =============================================================================
// Scalability demo (only where the server enables it)
// =============================================================================

export function useDemoStatus(enabled: boolean) {
  return useQuery({
    queryKey: keys.demo,
    queryFn: () => api.get<DemoRunStatus>('/admin/demo/status'),
    enabled,
    refetchInterval: (q) => (q.state.data?.running ? 3_000 : false),
  });
}

export function useDemoControl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { action: 'start'; config: DemoRunConfig } | { action: 'stop' }) =>
      v.action === 'start'
        ? api.post<DemoRunStatus>('/admin/demo/start', v.config)
        : api.post<DemoRunStatus>('/admin/demo/stop'),
    onSuccess: (status) => qc.setQueryData(keys.demo, status),
  });
}
