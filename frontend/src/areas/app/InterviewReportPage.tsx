/**
 * One interview: written report, transcript, code, integrity, recording, and the
 * organization's hiring decision. Routed at /app/interviews/:sessionId and
 * /platform/interviews/:sessionId. Plan: context/dashboard_rebuild_plan.md, 3.1.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { ApiError } from '@/lib/api';
import { formatDateTime, minutesSince, percent, roundLabel } from '@/lib/format';
import type {
  CheatFlagEntry,
  FlagEvidence,
  VerificationProbe,
  CodeVersion,
  HiringDecision,
  InterviewDetail,
  TimestampNoteEntry,
  TranscriptEntry,
} from '@/types';
import {
  Button,
  ButtonLink,
  DataTable,
  DefinitionList,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Section,
  Spinner,
  StatusLabel,
  Tabs,
  Textarea,
  cx,
  useToast,
  type Column,
  type TabItem,
  type Tone,
} from '@/ui';
import { useInterviewDetail, useRetryReport, useSetDecision } from '../shared/data';
import { endReason } from '../shared/endReasons';

type TabKey = 'summary' | 'transcript' | 'coding' | 'integrity' | 'recording' | 'internals';

const IDLE_MINUTES = 15;

// =============================================================================
// Labels
// =============================================================================

const RECOMMENDATION: Record<string, { word: string; tone: Tone }> = {
  strong_yes: { word: 'Strong yes', tone: 'good' },
  yes: { word: 'Yes', tone: 'good' },
  maybe: { word: 'Maybe', tone: 'warn' },
  no: { word: 'No', tone: 'bad' },
  strong_no: { word: 'Strong no', tone: 'bad' },
};

const INTEGRITY_RECOMMENDATION: Record<string, { word: string; tone: Tone }> = {
  proceed: { word: 'Proceed', tone: 'good' },
  review: { word: 'Review', tone: 'warn' },
  flag: { word: 'Flag', tone: 'bad' },
  reject: { word: 'Reject', tone: 'bad' },
};

const DECISIONS: Array<{ key: HiringDecision; word: string; tone: Tone }> = [
  { key: 'advance', word: 'Advance', tone: 'good' },
  { key: 'hold', word: 'Hold', tone: 'warn' },
  { key: 'reject', word: 'Reject', tone: 'bad' },
];

const FLAG_LABELS: Record<string, string> = {
  multiple_faces: 'Another person in view',
  no_face: 'No face detected',
  phone_detected: 'Phone in view',
  earphone_detected: 'Earphone detected',
  tab_switch: 'Tab switch',
  screen_share: 'Screen share',
  voice_change: 'Voice change',
  copy_paste: 'Copy and paste',
  ai_assistance: 'AI assistance',
  suspicious_timing: 'Suspicious timing',
  blocked_app: 'Blocked app open',
  second_screen: 'Another laptop or screen',
  app_closed: 'App closed early',
  exit_attempt: 'Tried to close the app',
  emergency_exit: 'Emergency exit used',
  lock_expired: 'Lock time limit reached',
  browser_mode: 'No locked app',
};

const PROBE_OUTCOME: Record<string, { word: string; tone: Tone }> = {
  passed: { word: 'Explained it', tone: 'good' },
  failed: { word: 'Could not explain it', tone: 'bad' },
  unanswered: { word: 'Did not answer', tone: 'bad' },
  inconclusive: { word: 'Not settled', tone: 'warn' },
  asked: { word: 'Not answered before the interview moved on', tone: 'neutral' },
  answered: { word: 'Not assessed', tone: 'neutral' },
};

const SEVERITY_TONE: Record<string, Tone> = { low: 'neutral', medium: 'warn', high: 'bad', critical: 'bad' };

/** "rubric_scores" → "Rubric scores" */
const humanize = (key: string) => {
  const s = key.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
};

function duration(start: string | null, end: string | null): string {
  if (!start) return '—';
  const minutes = end ? (new Date(end).getTime() - new Date(start).getTime()) / 60_000 : minutesSince(start);
  if (minutes == null || Number.isNaN(minutes) || minutes < 0) return '—';
  if (minutes < 1) return 'under a minute';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  return `${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} min`;
}

function statusOf(d: InterviewDetail): { word: string; tone: Tone } {
  if (d.status === 'completed') {
    const r = endReason(d.end_reason);
    return r ? { word: r.status, tone: r.tone } : { word: 'Completed', tone: 'good' };
  }
  const idle = minutesSince(d.last_activity);
  if (idle != null && idle > IDLE_MINUTES) return { word: 'No activity', tone: 'warn' };
  return { word: 'Live', tone: 'live' };
}

/** Score as 0–1 or 0–100 → "86%" */
const score = (v: unknown) =>
  typeof v === 'number' ? (v > 1 ? `${Math.round(v)}%` : percent(v)) : '—';

// =============================================================================
// Page
// =============================================================================

export function InterviewReportPage() {
  const { sessionId = '' } = useParams();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const area = pathname.startsWith('/platform') ? '/platform' : '/app';
  const back = { to: `${area}/interviews`, label: 'Interviews' };
  const query = useInterviewDetail(sessionId);
  const [tab, setTab] = useState<TabKey>('summary');
  const [seekTo, setSeekTo] = useState<number | null>(null);

  if (query.isLoading) {
    return (
      <div className="py-16">
        <Spinner label="Loading the interview" />
      </div>
    );
  }

  if (query.error) {
    const notFound = query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 403);
    return (
      <>
        <PageHeader title="Interview" back={back} />
        {notFound ? (
          <EmptyState
            title="Interview not found"
            body="It may have been removed, or it belongs to another organization."
            action={<ButtonLink to={back.to}>Back to interviews</ButtonLink>}
          />
        ) : (
          <ErrorState title="The interview didn’t load" error={query.error} onRetry={() => query.refetch()} />
        )}
      </>
    );
  }

  const d = query.data!;
  const status = statusOf(d);
  const coding = d.interview_mode === 'round2_dsa';
  const messages = d.transcript.messages.filter((m) => m.role === 'user' || m.role === 'assistant');

  const tabs: TabItem<TabKey>[] = [
    { key: 'summary', label: 'Summary' },
    { key: 'transcript', label: 'Transcript', count: messages.length },
    ...(coding ? [{ key: 'coding' as const, label: 'Coding' }] : []),
    { key: 'integrity', label: 'Integrity', count: d.integrity.cheat_flags.length },
    { key: 'recording', label: 'Recording' },
    ...(user?.is_platform_admin && d.internals ? [{ key: 'internals' as const, label: 'Internals' }] : []),
  ];
  const current = tabs.some((t) => t.key === tab) ? tab : 'summary';

  return (
    <>
      <PageHeader
        back={back}
        title={d.candidate_name || 'Unnamed candidate'}
        meta={
          <>
            <StatusLabel tone={status.tone}>{status.word}</StatusLabel>
            {d.role_title && <span>{d.role_title}</span>}
            <span>{roundLabel(d.interview_mode)} round</span>
            <span>{formatDateTime(d.started_at ?? d.created_at)}</span>
            <span>{duration(d.started_at ?? d.created_at, d.ended_at)}</span>
          </>
        }
      />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <Tabs label="Interview report" items={tabs} value={current} onChange={setTab} />
          <div className="pt-6" role="tabpanel">
            {current === 'summary' && <SummaryTab d={d} />}
            {current === 'transcript' && <TranscriptTab messages={messages} live={d.live} />}
            {current === 'coding' && <CodingTab d={d} />}
            {current === 'integrity' && (
              <IntegrityTab
                d={d}
                onOpenRecording={(seconds) => {
                  setSeekTo(seconds);
                  setTab('recording');
                }}
              />
            )}
            {current === 'recording' && <RecordingTab d={d} startAt={seekTo} />}
            {current === 'internals' && <Json value={d.internals} />}
          </div>
        </div>

        <aside className="min-w-0">
          <DefinitionList
            items={[
              { term: 'Email', value: d.candidate_email || null },
              { term: 'Role', value: d.role_title || null },
              { term: 'Round', value: roundLabel(d.interview_mode) },
              { term: 'Started', value: formatDateTime(d.started_at ?? d.created_at) },
              { term: 'Ended', value: d.ended_at ? formatDateTime(d.ended_at) : null },
              { term: 'Ended because', value: endReason(d.end_reason)?.label ?? null },
              { term: 'Turns', value: <span className="tabular">{d.turn_count}</span> },
              { term: 'Integrity', value: <span className="tabular">{score(d.integrity.integrity_score)}</span> },
              {
                term: 'Report says',
                value: d.report?.recommendation ? (
                  <StatusLabel tone={RECOMMENDATION[d.report.recommendation]?.tone}>
                    {RECOMMENDATION[d.report.recommendation]?.word ?? d.report.recommendation}
                  </StatusLabel>
                ) : null,
              },
            ]}
          />
          <DecisionPanel d={d} />
        </aside>
      </div>
    </>
  );
}

// =============================================================================
// Decision
// =============================================================================

function DecisionPanel({ d }: { d: InterviewDetail }) {
  const save = useSetDecision(d.session_id);
  const toast = useToast();
  const [choice, setChoice] = useState<HiringDecision | null>(d.decision?.decision ?? null);
  const [note, setNote] = useState(d.decision?.note ?? '');

  // Follow the saved decision (e.g. after saving, or a teammate's change on refresh)
  useEffect(() => {
    setChoice(d.decision?.decision ?? null);
    setNote(d.decision?.note ?? '');
  }, [d.decision?.decision, d.decision?.note]);

  const dirty = choice !== (d.decision?.decision ?? null) || note.trim() !== (d.decision?.note ?? '');
  const saved = DECISIONS.find((x) => x.key === d.decision?.decision);

  const submit = (decision: HiringDecision | null) =>
    save.mutate(
      { decision, note: decision ? note : '' },
      {
        onSuccess: () => toast.show(decision ? 'Decision saved' : 'Decision cleared', 'good'),
        onError: (e) => toast.show(e instanceof Error ? e.message : 'The decision wasn’t saved', 'bad'),
      },
    );

  return (
    <section className="mt-8">
      <h2 className="font-ui text-lead font-semibold text-ink">Decision</h2>
      {d.decision && saved ? (
        <div className="mt-2">
          <StatusLabel tone={saved.tone}>{saved.word}</StatusLabel>
          <p className="mt-1 text-meta text-muted">
            {d.decision.decided_by?.name ?? 'Someone'}, {formatDateTime(d.decision.decided_at)}
          </p>
          {!d.can_decide && d.decision.note && (
            <p className="mt-2 whitespace-pre-line text-body text-ink">{d.decision.note}</p>
          )}
        </div>
      ) : (
        <p className="mt-1 text-meta text-muted">No decision yet.</p>
      )}

      {d.can_decide ? (
        <div className="mt-4 space-y-4">
          <div role="radiogroup" aria-label="Decision" className="flex gap-2">
            {DECISIONS.map((x) => (
              <button
                key={x.key}
                type="button"
                role="radio"
                aria-checked={choice === x.key}
                onClick={() => setChoice(x.key)}
                className={cx(
                  'h-9 flex-1 rounded-ui border text-body transition-colors',
                  choice === x.key
                    ? 'border-accent bg-accent text-on-accent'
                    : 'border-line-strong text-ink hover:bg-sunken',
                )}
              >
                {x.word}
              </button>
            ))}
          </div>
          <Field label="Note" optional hint="Why, for your team. Candidates don’t see it.">
            {(p) => (
              <Textarea
                id={p.id}
                aria-describedby={p.describedBy}
                rows={3}
                maxLength={4000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            )}
          </Field>
          <div className="flex gap-2">
            <Button variant="primary" disabled={!choice || !dirty} loading={save.isPending} onClick={() => submit(choice)}>
              Save decision
            </Button>
            {d.decision && (
              <Button variant="ghost" disabled={save.isPending} onClick={() => submit(null)}>
                Clear
              </Button>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-3 text-meta text-muted">Only the candidate’s organization can record a decision.</p>
      )}
    </section>
  );
}

// =============================================================================
// Summary
// =============================================================================

const errorText = (e: unknown) => (e instanceof Error ? e.message : 'That didn’t work. Try again in a moment.');

function ReportNotice({ d }: { d: InterviewDetail }) {
  const retry = useRetryReport(d.session_id);
  if (d.report_status === 'failed') {
    return (
      <EmptyState
        title="The report couldn’t be written"
        body={
          retry.error
            ? errorText(retry.error)
            : 'Writing the report failed or is taking much longer than usual. The transcript and integrity tabs are complete; try writing the report again.'
        }
        action={
          d.can_decide ? (
            <Button variant="primary" loading={retry.isPending} onClick={() => retry.mutate()}>
              Try again
            </Button>
          ) : undefined
        }
      />
    );
  }
  if (d.report_status === 'pending') {
    return (
      <EmptyState
        title="The report is being written"
        body="The interview has ended. The written report usually appears within a few minutes, and this page shows it as soon as it’s ready."
      />
    );
  }
  return (
    <EmptyState
      title={d.live ? 'Interview in progress' : 'No report'}
      body={
        d.live
          ? 'The written report is prepared when the interview ends. The transcript and integrity tabs update while it runs.'
          : 'This interview ended without a written report.'
      }
    />
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-body text-ink">
      {items.map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ul>
  );
}

/** Detailed sections are free-form: text, lists or nested objects. */
function Prose({ value }: { value: unknown }): ReactNode {
  if (value == null || value === '') return <span className="text-muted">—</span>;
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    return <p className="whitespace-pre-line text-body text-ink">{String(value)}</p>;
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v === 'string')) return <BulletList items={value as string[]} />;
    return (
      <div className="space-y-3">
        {value.map((v, i) => (
          <Prose key={i} value={v} />
        ))}
      </div>
    );
  }
  return (
    <dl className="space-y-3">
      {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
        <div key={k}>
          <dt className="text-meta font-medium text-muted">{humanize(k)}</dt>
          <dd className="mt-0.5">
            <Prose value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

interface ScoreRow {
  name: string;
  value: string;
  detail?: string;
}

function ScoreTable({ rows, caption }: { rows: ScoreRow[]; caption: string }) {
  const columns: Column<ScoreRow>[] = [
    { key: 'name', header: 'Area', render: (r) => r.name },
    { key: 'detail', header: 'Detail', render: (r) => r.detail ?? '', hideBelow: 'md' },
    { key: 'value', header: 'Score', render: (r) => r.value, align: 'right', numeric: true, width: 'w-24' },
  ];
  return <DataTable caption={caption} columns={columns} rows={rows} rowKey={(r) => r.name} />;
}

/**
 * Coding round facts. The DSA final report is stored in the analytics slot; if it
 * wasn't produced (or isn't ready), fall back to the live coding state.
 */
function codingFacts(d: InterviewDetail): Record<string, any> {
  const a = d.analytics ?? {};
  if (a.problem_title) return a;
  const s = d.dsa_state ?? {};
  const last = s.last_execution_result ?? {};
  const passed = Array.isArray(last.test_results)
    ? last.test_results.filter((t: { passed?: boolean }) => t.passed).length
    : last.tests_passed;
  return {
    problem_title: s.problem_title,
    difficulty: s.difficulty,
    hints_used: s.hints_used,
    mistakes: s.mistakes,
    evidence_citations: s.evidence_citations,
    dimension_scores: s.scores,
    tests_total: last.tests_total,
    tests_passed: last.tests_total != null ? passed : undefined,
    candidate_time_complexity: s.actual_complexity ?? s.candidate_complexity_claim,
    reference_time_complexity: s._ref_time_complexity,
    final_code: s.current_code,
  };
}

function SummaryTab({ d }: { d: InterviewDetail }) {
  const r = d.report;
  const coding = d.interview_mode === 'round2_dsa';
  const a = coding ? codingFacts(d) : (d.analytics ?? {});

  const rubric: ScoreRow[] = Object.entries((a.rubric_scores ?? {}) as Record<string, unknown>).map(([k, v]) => ({
    name: humanize(k),
    value: typeof v === 'number' ? (v <= 1 ? percent(v) : v.toFixed(1)) : typeof v === 'object' && v && 'score' in v ? String((v as { score: unknown }).score) : String(v ?? '—'),
  }));
  const dimensions: ScoreRow[] = Object.entries((a.dimension_scores ?? {}) as Record<string, unknown>).map(([k, v]) => ({
    name: humanize(k),
    value: typeof v === 'number' ? score(v) : String(v ?? '—'),
  }));
  const tree = d.skill_tree;
  const skills: ScoreRow[] = Object.entries(tree?.current_levels ?? {}).map(([k, level]) => ({
    name: humanize(k),
    // No evidence at all: the skill wasn't assessed, not "level 0"
    value: tree?.evidence_counts?.[k] ? `${level} / 5` : 'Not assessed',
    detail: [
      tree?.skill_weights?.[k] != null ? `weight ${percent(tree.skill_weights[k])}` : null,
      tree?.evidence_counts?.[k] != null ? `${tree.evidence_counts[k]} pieces of evidence` : null,
    ]
      .filter(Boolean)
      .join(', '),
  }));

  const c = d.completion;

  return (
    <>
      {c?.incomplete && (
        <div role="note" className="mb-8 border border-bad/40 bg-bad/5 px-4 py-3">
          <p className="text-body font-medium text-ink">
            Incomplete interview: {endReason(c.end_reason)?.label.toLowerCase() ?? 'ended early'}
            {c.minutes != null ? ` after ${Math.round(c.minutes)} minutes` : ''}.
          </p>
          <p className="mt-0.5 text-meta text-muted">
            {[
              c.unanswered_questions ? `${c.unanswered_questions} question${c.unanswered_questions === 1 ? '' : 's'} unanswered` : null,
              c.absences ? `away ${c.absences} time${c.absences === 1 ? '' : 's'}` : null,
              c.skills_not_assessed.length ? `not assessed: ${c.skills_not_assessed.map(humanize).join(', ')}` : null,
            ]
              .filter(Boolean)
              .join(' · ') || 'Judge the results below with that in mind.'}
          </p>
        </div>
      )}
      {r ? (
        <>
          <Section title="Summary">
            <Prose value={r.summary} />
          </Section>
          {(r.strengths?.length || r.concerns?.length) && (
            <div className="mb-10 grid gap-8 md:grid-cols-2">
              <div>
                <h2 className="mb-3 font-ui text-lead font-semibold text-ink">Strengths</h2>
                {r.strengths?.length ? <BulletList items={r.strengths} /> : <p className="text-meta text-muted">None noted.</p>}
              </div>
              <div>
                <h2 className="mb-3 font-ui text-lead font-semibold text-ink">Concerns</h2>
                {r.concerns?.length ? <BulletList items={r.concerns} /> : <p className="text-meta text-muted">None noted.</p>}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="mb-10">
          <ReportNotice d={d} />
        </div>
      )}

      {coding && a.narrative_summary && !r?.summary && (
        <Section title="Summary">
          <Prose value={a.narrative_summary} />
        </Section>
      )}

      {coding && dimensions.length > 0 && (
        <Section title="Coding scores" description={a.final_score_percentage != null ? `Overall ${score(a.final_score_percentage)}` : undefined}>
          <ScoreTable caption="Coding scores by dimension" rows={dimensions} />
        </Section>
      )}

      {!coding && rubric.length > 0 && (
        <Section title="Rubric">
          <ScoreTable caption="Rubric scores" rows={rubric} />
        </Section>
      )}

      {skills.length > 0 && (
        <Section
          title="Skills"
          description={[
            tree?.score_percentage != null ? `Overall ${score(tree.score_percentage)}` : null,
            tree?.elo_rating != null ? `rating ${Math.round(tree.elo_rating)}` : null,
          ]
            .filter(Boolean)
            .join(', ')}
        >
          <ScoreTable caption="Skill levels" rows={skills} />
        </Section>
      )}

      {r?.detailed_sections && Object.keys(r.detailed_sections).length > 0 && (
        <Section title="Details">
          <Prose value={r.detailed_sections} />
        </Section>
      )}
    </>
  );
}

// =============================================================================
// Transcript
// =============================================================================

function TranscriptTab({ messages, live }: { messages: TranscriptEntry[]; live: boolean }) {
  if (!messages.length) {
    return (
      <EmptyState
        title="No transcript yet"
        body={live ? 'Messages appear here as the interview goes on.' : 'Nothing was said in this interview.'}
      />
    );
  }
  return (
    <ol className="divide-y divide-line border-y border-line">
      {messages.map((m, i) => {
        const candidate = m.role === 'user';
        return (
          <li key={i} className="grid gap-1 py-4 sm:grid-cols-[8rem_minmax(0,1fr)] sm:gap-6">
            <div className="text-meta">
              <p className={cx('font-medium', candidate ? 'text-ink' : 'text-accent')}>
                {candidate ? 'Candidate' : 'Presence'}
              </p>
              {m.timestamp && <p className="tabular text-muted">{formatDateTime(m.timestamp)}</p>}
            </div>
            <p className="whitespace-pre-line text-body text-ink">{m.content}</p>
          </li>
        );
      })}
      {live && (
        <li className="py-3">
          <StatusLabel tone="live">Live, updating</StatusLabel>
        </li>
      )}
    </ol>
  );
}

// =============================================================================
// Coding
// =============================================================================

function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="max-h-[32rem] overflow-auto border border-line bg-sunken p-4 font-mono text-meta leading-relaxed text-ink">
      <code>{code}</code>
    </pre>
  );
}

interface Evidence {
  dimension?: string;
  criterion?: string;
  verdict?: string;
  quote?: string;
  /** Older name for the quote */
  evidence?: string;
  confidence?: number;
  reasoning?: string;
}

function CodingTab({ d }: { d: InterviewDetail }) {
  const a = codingFacts(d);
  const versions: CodeVersion[] = d.dsa_state?.code_versions ?? [];
  const [picked, setPicked] = useState<number | null>(null);
  const shown = useMemo(() => versions.find((v) => v.version === picked) ?? null, [versions, picked]);
  const finalCode: string = a.final_code || versions[versions.length - 1]?.code || d.dsa_state?.current_code || '';
  const evidence: Evidence[] = Array.isArray(a.evidence_citations) ? a.evidence_citations : [];

  const versionColumns: Column<CodeVersion>[] = [
    { key: 'version', header: 'Version', render: (v) => `#${v.version}`, numeric: true, width: 'w-24' },
    { key: 'time', header: 'Run at', render: (v) => formatDateTime(v.timestamp) },
    {
      key: 'tests',
      header: 'Tests',
      align: 'right',
      numeric: true,
      render: (v) =>
        v.execution_result?.tests_total != null
          ? `${v.execution_result.tests_passed ?? 0} / ${v.execution_result.tests_total}`
          : '—',
    },
    {
      key: 'view',
      header: <span className="sr-only">View</span>,
      align: 'right',
      render: (v) => (
        <Button size="sm" variant="ghost" onClick={() => setPicked(picked === v.version ? null : v.version)}>
          {picked === v.version ? 'Hide' : 'View'}
        </Button>
      ),
    },
  ];

  const evidenceColumns: Column<Evidence>[] = [
    { key: 'dim', header: 'Dimension', render: (e) => humanize(e.dimension ?? '') || '—' },
    { key: 'crit', header: 'Criterion', render: (e) => e.criterion ?? '—', hideBelow: 'md' },
    { key: 'verdict', header: 'Verdict', render: (e) => e.verdict ?? '—' },
    {
      key: 'quote',
      header: 'Evidence',
      render: (e) => (
        <span>
          {(e.quote ?? e.evidence) && <q className="text-ink">{e.quote ?? e.evidence}</q>}
          {e.reasoning && <span className="block text-meta text-muted">{e.reasoning}</span>}
        </span>
      ),
    },
  ];

  if (!a.problem_title && !finalCode && !versions.length) {
    return (
      <EmptyState
        title="No code yet"
        body={d.live ? 'The candidate’s code appears here once they run it.' : 'No code was written in this interview.'}
      />
    );
  }

  return (
    <>
      <Section title={a.problem_title ?? 'Problem'} description={a.difficulty ? humanize(String(a.difficulty)) : undefined}>
        <DefinitionList
          items={[
            {
              term: 'Tests passed',
              value: a.tests_total != null ? <span className="tabular">{`${a.tests_passed ?? 0} / ${a.tests_total}`}</span> : null,
            },
            { term: 'Runtime', value: a.runtime_ms != null ? <span className="tabular">{`${Number(a.runtime_ms).toFixed(1)} ms`}</span> : null },
            { term: 'Candidate’s complexity', value: a.candidate_time_complexity ?? a.candidate_complexity ?? null },
            { term: 'Expected complexity', value: a.reference_time_complexity ?? a.reference_complexity ?? null },
            { term: 'Hints used', value: a.hints_used != null ? <span className="tabular">{String(a.hints_used)}</span> : null },
            { term: 'Overall', value: a.final_score_percentage != null ? score(a.final_score_percentage) : null },
          ]}
        />
        {(a.compilation_error || a.runtime_error) && (
          <p className="mt-3 text-meta text-bad">{a.compilation_error || a.runtime_error}</p>
        )}
      </Section>

      {finalCode && (
        <Section title="Final code">
          <CodeBlock code={finalCode} />
        </Section>
      )}

      {versions.length > 0 && (
        <Section title="Runs" description="Each time the candidate ran their code.">
          <DataTable caption="Code runs" columns={versionColumns} rows={versions} rowKey={(v) => String(v.version)} />
          {shown && (
            <div className="mt-4">
              <CodeBlock code={shown.code} />
            </div>
          )}
        </Section>
      )}

      {Array.isArray(a.mistakes) && a.mistakes.length > 0 && (
        <Section title="Mistakes">
          <BulletList
            items={a.mistakes.map((m: unknown) =>
              typeof m === 'string' ? m : String((m as { description?: string }).description ?? JSON.stringify(m)),
            )}
          />
        </Section>
      )}

      {evidence.length > 0 && (
        <Section title="Evidence">
          <DataTable caption="Evidence for the coding scores" columns={evidenceColumns} rows={evidence} rowKey={(e) => `${e.dimension}-${e.criterion}-${e.quote ?? e.evidence}`} />
        </Section>
      )}

      {(a.strengths?.length || a.weaknesses?.length) && (
        <div className="mb-10 grid gap-8 md:grid-cols-2">
          <div>
            <h2 className="mb-3 font-ui text-lead font-semibold text-ink">Strengths</h2>
            <Prose value={a.strengths} />
          </div>
          <div>
            <h2 className="mb-3 font-ui text-lead font-semibold text-ink">Weaknesses</h2>
            <Prose value={a.weaknesses} />
          </div>
        </div>
      )}
    </>
  );
}

// =============================================================================
// Integrity
// =============================================================================

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

const evidenceOf = (f: CheatFlagEntry): FlagEvidence | null =>
  f.evidence && typeof f.evidence === 'object' ? f.evidence : null;

function IntegrityTab({ d, onOpenRecording }: { d: InterviewDetail; onOpenRecording: (seconds: number) => void }) {
  const [proof, setProof] = useState<CheatFlagEntry | null>(null);
  const { cheat_flags: flags, integrity_report: report, timestamp_notes: notes, integrity_score } = d.integrity;
  const rec = report?.recommendation ? INTEGRITY_RECOMMENDATION[report.recommendation] : null;
  const timings = d.integrity.response_timings ?? [];
  const probes = d.integrity.verification_probes ?? [];

  const flagColumns: Column<CheatFlagEntry>[] = [
    { key: 'type', header: 'What', render: (f) => FLAG_LABELS[f.flag_type] ?? humanize(f.flag_type) },
    {
      key: 'severity',
      header: 'Severity',
      render: (f) => <StatusLabel tone={SEVERITY_TONE[f.severity ?? ''] ?? 'neutral'}>{humanize(f.severity ?? 'unknown')}</StatusLabel>,
    },
    { key: 'desc', header: 'Detail', render: (f) => f.description ?? '', hideBelow: 'md' },
    { key: 'when', header: 'When', render: (f) => (f.timestamp ? formatDateTime(f.timestamp) : f.turn_number != null ? `Turn ${f.turn_number}` : '—') },
    {
      key: 'proof',
      header: 'Proof',
      render: (f) => {
        const ev = evidenceOf(f);
        if (ev?.photo_key && f.id) {
          return (
            <Button size="sm" variant="ghost" onClick={() => setProof(f)}>
              View photo
            </Button>
          );
        }
        if (ev?.recording_seconds != null && d.recording.url) {
          return (
            <Button size="sm" variant="ghost" onClick={() => onOpenRecording(ev.recording_seconds!)}>
              Recording at {clock(ev.recording_seconds)}
            </Button>
          );
        }
        return <span className="text-muted">—</span>;
      },
    },
  ];

  const noteColumns: Column<TimestampNoteEntry>[] = [
    {
      key: 'at',
      header: 'At',
      numeric: true,
      width: 'w-24',
      render: (n) =>
        n.video_seconds != null
          ? `${Math.floor(n.video_seconds / 60)}:${String(Math.floor(n.video_seconds % 60)).padStart(2, '0')}`
          : n.turn_number != null
            ? `Turn ${n.turn_number}`
            : '—',
    },
    { key: 'tag', header: 'Tag', render: (n) => (n.tag ? humanize(n.tag) : '—'), hideBelow: 'sm' },
    { key: 'note', header: 'Note', render: (n) => n.content ?? '' },
  ];

  return (
    <>
      <Section title="Overview">
        <DefinitionList
          items={[
            { term: 'Integrity score', value: <span className="tabular">{score(integrity_score ?? report?.integrity_score)}</span> },
            { term: 'Recommendation', value: rec ? <StatusLabel tone={rec.tone}>{rec.word}</StatusLabel> : null },
            { term: 'Flags', value: <span className="tabular">{flags.length}</span> },
            { term: 'Times away', value: <span className="tabular">{d.completion?.absences ?? 0}</span> },
            { term: 'Unanswered questions', value: <span className="tabular">{d.completion?.unanswered_questions ?? 0}</span> },
          ]}
        />
        {report?.summary && <p className="mt-4 text-body text-ink">{report.summary}</p>}
      </Section>

      <Section title="Flags">
        <DataTable
          caption="Integrity flags"
          columns={flagColumns}
          rows={flags}
          rowKey={(f) => f.flag_id ?? `${f.flag_type}-${f.timestamp}-${f.turn_number}`}
          empty={<EmptyState title="No flags" body="Nothing unusual was detected during this interview." />}
        />
      </Section>

      {proof && (
        <ProofDrawer
          sessionId={d.session_id}
          flag={proof}
          canPlay={!!d.recording.url}
          onClose={() => setProof(null)}
          onOpenRecording={(seconds) => {
            setProof(null);
            onOpenRecording(seconds);
          }}
        />
      )}

      {probes.length > 0 && (
        <Section
          title="Follow-up checks"
          description="When a long, polished answer follows a long silence, the interviewer asks a follow-up that only someone who understands that answer can handle. A good answer clears the flag."
        >
          <ol className="divide-y divide-line border-y border-line">
            {probes.map((p) => (
              <ProbeRow key={p.flag_id ?? String(p.turn)} probe={p} />
            ))}
          </ol>
        </Section>
      )}

      {timings.length > 0 && (
        <Section
          title="Response times"
          description="From the end of each question to the candidate's first word. A long silence before a long, polished answer can mean the answer was read from somewhere."
        >
          <DataTable
            caption="Response times"
            rows={timings}
            rowKey={(t) => String(t.turn)}
            columns={[
              { key: 'turn', header: 'Turn', numeric: true, width: 'w-20', render: (t) => t.turn },
              {
                key: 'latency',
                header: 'Before answering',
                numeric: true,
                align: 'right',
                sortValue: (t) => t.latency_ms,
                render: (t) => (
                  <span className={t.latency_ms >= 20_000 ? 'text-warn' : undefined}>{(t.latency_ms / 1000).toFixed(1)} s</span>
                ),
              },
              { key: 'words', header: 'Answer length', numeric: true, align: 'right', sortValue: (t) => t.words, render: (t) => `${t.words} words` },
            ]}
          />
        </Section>
      )}

      {notes.length > 0 && (
        <Section title="Notes" description="Moments marked during the interview.">
          <DataTable caption="Timestamp notes" columns={noteColumns} rows={notes} rowKey={(n) => `${n.video_seconds}-${n.turn_number}-${n.content}`} />
        </Section>
      )}
    </>
  );
}

/** A flagged answer and the follow-up that tested it, side by side. */
function ProbeRow({ probe }: { probe: VerificationProbe }) {
  const outcome = PROBE_OUTCOME[probe.outcome] ?? { word: humanize(probe.outcome), tone: 'neutral' as Tone };
  const seconds = (ms: number) => `${(ms / 1000).toFixed(0)} s`;
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <StatusLabel tone={outcome.tone}>{outcome.word}</StatusLabel>
        {probe.turn != null && <span className="text-meta text-muted">Turn {probe.turn}</span>}
      </div>
      {probe.reason && <p className="mt-1 text-body text-ink">{probe.reason}</p>}
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-meta font-medium text-muted">
            First answer: {probe.words} words after {seconds(probe.latency_ms)} of silence
          </p>
          <p className="mt-1 text-body text-ink">{probe.answer}</p>
        </div>
        <div>
          <p className="text-meta font-medium text-muted">
            Follow-up
            {probe.probe_latency_ms != null && `: answered after ${seconds(probe.probe_latency_ms)}`}
          </p>
          {probe.question && <p className="mt-1 text-body text-muted">{probe.question}</p>}
          <p className="mt-1 text-body text-ink">
            {probe.probe_answer || <span className="text-muted">No answer.</span>}
          </p>
        </div>
      </div>
    </li>
  );
}

/** The frame a camera check flagged, with the detections drawn over it. */
function ProofDrawer({
  sessionId,
  flag,
  canPlay,
  onClose,
  onOpenRecording,
}: {
  sessionId: string;
  flag: CheatFlagEntry;
  canPlay: boolean;
  onClose: () => void;
  onOpenRecording: (seconds: number) => void;
}) {
  const ev = evidenceOf(flag) ?? {};
  const [failed, setFailed] = useState(false);
  const src = `/api/org/interviews/${encodeURIComponent(sessionId)}/evidence/${encodeURIComponent(flag.id ?? '')}`;
  const shown = (ev.detections ?? []).filter((x) => x.label !== 'face');

  return (
    <Drawer
      open
      onClose={onClose}
      width="lg"
      title={FLAG_LABELS[flag.flag_type] ?? humanize(flag.flag_type)}
      description={flag.timestamp ? `Captured ${formatDateTime(flag.timestamp)}` : undefined}
      footer={
        ev.recording_seconds != null && canPlay ? (
          <Button variant="primary" onClick={() => onOpenRecording(ev.recording_seconds!)}>
            Watch the recording at {clock(ev.recording_seconds)}
          </Button>
        ) : undefined
      }
    >
      {failed ? (
        <ErrorState title="The photo didn’t load" error="It may no longer be stored." />
      ) : (
        <figure className="relative border border-line bg-black">
          <img src={src} alt={`Camera frame: ${flag.description ?? flag.flag_type}`} className="block w-full" onError={() => setFailed(true)} />
          {shown.map((x, i) => (
            <span
              key={i}
              aria-hidden
              className="absolute border-2 border-warn"
              style={{
                left: `${x.box[0] * 100}%`,
                top: `${x.box[1] * 100}%`,
                width: `${(x.box[2] - x.box[0]) * 100}%`,
                height: `${(x.box[3] - x.box[1]) * 100}%`,
              }}
            >
              <span className="absolute -top-5 left-0 whitespace-nowrap bg-warn px-1 text-[11px] font-medium text-on-accent">
                {x.label} {Math.round(x.score * 100)}%
              </span>
            </span>
          ))}
        </figure>
      )}
      <p className="mt-3 text-meta text-muted">
        Boxes are drawn on top for viewing; the stored photo is the unedited frame. A still can mislead (a wallet can
        look like a phone), so check the recording before deciding.
      </p>
      <DefinitionList
        className="mt-4"
        items={[
          { term: 'Confidence', value: flag.confidence != null ? `${Math.round(flag.confidence * 100)}%` : null },
          { term: 'Found', value: shown.map((x) => `${x.label} ${Math.round(x.score * 100)}%`).join(', ') || null },
          { term: 'Detected by', value: ev.model ?? null },
          {
            term: 'Photo fingerprint',
            value: ev.sha256 ? <span className="break-all font-mono text-[12px]" title="SHA-256 of the stored photo">{ev.sha256}</span> : null,
          },
        ]}
      />
    </Drawer>
  );
}

// =============================================================================
// Recording
// =============================================================================

function RecordingTab({ d, startAt }: { d: InterviewDetail; startAt?: number | null }) {
  if (d.recording.url) {
    return (
      <>
        {startAt != null && (
          <p className="mb-2 text-meta text-muted">Starting a few seconds before {clock(startAt)}, where the flag was raised.</p>
        )}
        <video
          controls
          preload="metadata"
          src={d.recording.url}
          className="w-full border border-line bg-black"
          onLoadedMetadata={(e) => {
            if (startAt != null) e.currentTarget.currentTime = Math.max(0, startAt - 5);
          }}
        >
          Your browser can’t play this recording.
        </video>
        <p className="mt-2 text-meta text-muted">The link is temporary; reload the page if playback stops working.</p>
      </>
    );
  }
  const pending = d.live || ['recording', 'processing', 'starting'].includes(d.recording.status);
  return (
    <EmptyState
      title={pending ? 'Recording not ready' : 'No recording'}
      body={
        pending
          ? 'The recording is available a few minutes after the interview ends.'
          : 'This interview wasn’t recorded, or the recording is no longer kept.'
      }
    />
  );
}

// =============================================================================
// Internals (platform admins)
// =============================================================================

function Json({ value }: { value: unknown }) {
  return (
    <>
      <p className="mb-3 text-meta text-muted">The worker’s raw state for this session. Platform admins only.</p>
      <CodeBlock code={JSON.stringify(value, null, 2)} />
    </>
  );
}
