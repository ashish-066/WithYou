/**
 * Create or edit one coding problem: what the candidate sees, the ground truth
 * the interviewer checks against, tests, hints and the scoring rubric.
 * Routed at /platform/problems/new and /platform/problems/:problemId.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Trash2 } from 'lucide-react';
import { ApiError } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { CodingProblem, ProblemTestCase } from '@/types';
import {
  Button,
  ButtonLink,
  Checkbox,
  DefinitionList,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Section,
  Select,
  Spinner,
  Textarea,
  useToast,
} from '@/ui';
import { useDeleteProblem, usePlatformProblem, useSaveProblem } from '../shared/data';

const DEFAULT_RUBRIC: CodingProblem['scoring_rubric']['dimensions'] = [
  { name: 'problem_understanding', weight: 0.1, description: '' },
  { name: 'algorithm_selection', weight: 0.2, description: '' },
  { name: 'reasoning', weight: 0.2, description: '' },
  { name: 'code_correctness', weight: 0.2, description: '' },
  { name: 'complexity_analysis', weight: 0.1, description: '' },
  { name: 'edge_case_handling', weight: 0.1, description: '' },
  { name: 'optimization', weight: 0.05, description: '' },
  { name: 'communication', weight: 0.05, description: '' },
];

function blank(): CodingProblem {
  return {
    problem_id: '',
    title: '',
    statement: '',
    constraints: [],
    difficulty: 'medium',
    tags: [],
    reference_solution: { algorithm: '', time_complexity: '', space_complexity: '', code: '', explanation: '' },
    acceptable_alternatives: [],
    suboptimal_valid: [],
    expected_concepts: [],
    important_edge_cases: [],
    follow_up_questions: [],
    optimization_prompts: [],
    interview_objectives: [],
    public_test_cases: [{ input: '', expected_output: '', description: '' }],
    hidden_test_cases: [],
    hint_policy: { allowed: true, max_hints: 3, progressive: true, hints: [], hint_score_penalty: 0.05 },
    scoring_rubric: { dimensions: DEFAULT_RUBRIC },
  };
}

/** "Two Sum" → "two_sum" */
const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 80);

const toLines = (list: string[] | undefined) => (list ?? []).join('\n');
const fromLines = (text: string) =>
  text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

const humanize = (key: string) => {
  const s = key.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
};

function problems(p: CodingProblem): string[] {
  const out: string[] = [];
  if (!p.problem_id.trim()) out.push('Add an id.');
  else if (!/^[a-z0-9_-]+$/.test(p.problem_id)) out.push('The id can use only lowercase letters, digits, - and _.');
  if (!p.title.trim()) out.push('Add a title.');
  if (!p.statement.trim()) out.push('Add the problem statement.');
  const r = p.reference_solution;
  if (!r.algorithm.trim() || !r.time_complexity.trim() || !r.space_complexity.trim() || !r.code.trim())
    out.push('Complete the reference solution (approach, both complexities and code).');
  const tests = [...p.public_test_cases, ...p.hidden_test_cases];
  if (!tests.length) out.push('Add at least one test.');
  if (tests.some((t) => !t.expected_output.trim())) out.push('Every test needs an expected output.');
  const total = p.scoring_rubric.dimensions.reduce((a, d) => a + (Number(d.weight) || 0), 0);
  if (p.scoring_rubric.dimensions.length && Math.abs(total - 1) > 0.05)
    out.push(`Rubric weights must add up to 100% (now ${Math.round(total * 100)}%).`);
  return out;
}

// =============================================================================
// Page
// =============================================================================

export function ProblemEditorPage() {
  const { problemId } = useParams();
  const creating = !problemId;
  const query = usePlatformProblem(problemId ?? null);
  const back = { to: '/platform/problems', label: 'Problem library' };

  if (!creating && query.isLoading) {
    return (
      <div className="py-16">
        <Spinner label="Loading the problem" />
      </div>
    );
  }
  if (!creating && (query.error || !query.data)) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <>
        <PageHeader title="Problem" back={back} />
        {notFound ? (
          <EmptyState title="Problem not found" action={<ButtonLink to={back.to}>Back to the library</ButtonLink>} />
        ) : (
          <ErrorState title="The problem didn’t load" error={query.error} onRetry={() => query.refetch()} />
        )}
      </>
    );
  }

  return (
    <Editor
      key={problemId ?? 'new'}
      initial={query.data?.problem ?? blank()}
      usage={query.data?.usage}
      creating={creating}
    />
  );
}

function Editor({
  initial,
  usage,
  creating,
}: {
  initial: CodingProblem;
  usage?: { invites: number; interviews: number };
  creating: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const save = useSaveProblem();
  const remove = useDeleteProblem();
  const [p, setP] = useState<CodingProblem>(() => ({ ...blank(), ...initial }));
  const [idTouched, setIdTouched] = useState(!creating);
  const [showErrors, setShowErrors] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dirty, setDirty] = useState(false);

  const errors = useMemo(() => problems(p), [p]);

  // Warn before leaving the page (reload, close tab) with unsaved changes
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const update = (patch: Partial<CodingProblem>) => {
    setDirty(true);
    setP((old) => ({ ...old, ...patch }));
  };
  const setRef = (patch: Partial<CodingProblem['reference_solution']>) =>
    update({ reference_solution: { ...p.reference_solution, ...patch } });
  const setHints = (patch: Partial<CodingProblem['hint_policy']>) => update({ hint_policy: { ...p.hint_policy, ...patch } });

  const submit = () => {
    if (errors.length) {
      setShowErrors(true);
      return;
    }
    save.mutate(
      { create: creating, problem: p },
      {
        onSuccess: (res) => {
          setDirty(false);
          toast.show(creating ? 'Problem added' : 'Changes saved', 'good');
          if (creating) navigate(`/platform/problems/${encodeURIComponent(res.problem.problem_id)}`, { replace: true });
        },
        onError: (e) => toast.show(e instanceof Error ? e.message : 'The problem wasn’t saved', 'bad'),
      },
    );
  };

  const doDelete = () =>
    remove.mutate(p.problem_id, {
      onSuccess: () => {
        toast.show('Problem deleted', 'good');
        navigate('/platform/problems', { replace: true });
      },
      onError: (e) => toast.show(e instanceof Error ? e.message : 'The problem wasn’t deleted', 'bad'),
    });

  const rubricTotal = p.scoring_rubric.dimensions.reduce((a, d) => a + (Number(d.weight) || 0), 0);

  return (
    <>
      <PageHeader
        back={{ to: '/platform/problems', label: 'Problem library' }}
        title={creating ? 'New problem' : p.title || 'Untitled problem'}
        meta={!creating && <span className="font-mono">{p.problem_id}</span>}
        actions={
          <Button variant="primary" loading={save.isPending} onClick={submit} disabled={!creating && !dirty}>
            {creating ? 'Add problem' : 'Save changes'}
          </Button>
        }
      />

      {showErrors && errors.length > 0 && (
        <div role="alert" className="mb-8 border border-bad/40 bg-bad/5 px-4 py-3">
          <p className="text-body font-medium text-ink">Fix these before saving:</p>
          <ul className="mt-1 list-disc pl-5 text-meta text-ink">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <Section title="What the candidate sees">
            <div className="space-y-4">
              <div className="grid items-end gap-4 sm:grid-cols-2">
                <Field label="Title">
                  {(f) => (
                    <Input
                      id={f.id}
                      value={p.title}
                      onChange={(e) =>
                        update({ title: e.target.value, ...(idTouched ? {} : { problem_id: slug(e.target.value) }) })
                      }
                    />
                  )}
                </Field>
                <Field label="Id" hint={creating ? 'Used in invites. Can’t be changed later.' : undefined}>
                  {(f) => (
                    <Input
                      id={f.id}
                      aria-describedby={f.describedBy}
                      className="font-mono"
                      value={p.problem_id}
                      disabled={!creating}
                      onChange={(e) => {
                        setIdTouched(true);
                        update({ problem_id: e.target.value });
                      }}
                    />
                  )}
                </Field>
              </div>
              <div className="grid items-end gap-4 sm:grid-cols-2">
                <Field label="Difficulty">
                  {(f) => (
                    <Select
                      id={f.id}
                      value={p.difficulty}
                      onChange={(e) => update({ difficulty: e.target.value as CodingProblem['difficulty'] })}
                    >
                      <option value="easy">Easy</option>
                      <option value="medium">Medium</option>
                      <option value="hard">Hard</option>
                    </Select>
                  )}
                </Field>
                <Field label="Topics" optional hint="Comma-separated, e.g. array, hash table">
                  {(f) => (
                    <Input
                      id={f.id}
                      aria-describedby={f.describedBy}
                      value={p.tags.join(', ')}
                      onChange={(e) =>
                        update({
                          tags: e.target.value
                            .split(',')
                            .map((t) => t.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                  )}
                </Field>
              </div>
              <Field label="Statement" hint="Shown to the candidate as written.">
                {(f) => (
                  <Textarea
                    id={f.id}
                    aria-describedby={f.describedBy}
                    rows={8}
                    value={p.statement}
                    onChange={(e) => update({ statement: e.target.value })}
                  />
                )}
              </Field>
              <LinesField
                label="Constraints"
                hint="One per line, e.g. 2 ≤ n ≤ 10⁴"
                value={p.constraints}
                onChange={(constraints) => update({ constraints })}
              />
            </div>
          </Section>

          <Section title="Reference solution" description="Never shown to the candidate or spoken by the interviewer.">
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
                <Field label="Approach">
                  {(f) => (
                    <Input id={f.id} placeholder="hash_map" value={p.reference_solution.algorithm} onChange={(e) => setRef({ algorithm: e.target.value })} />
                  )}
                </Field>
                <Field label="Time">
                  {(f) => (
                    <Input id={f.id} placeholder="O(n)" value={p.reference_solution.time_complexity} onChange={(e) => setRef({ time_complexity: e.target.value })} />
                  )}
                </Field>
                <Field label="Space">
                  {(f) => (
                    <Input id={f.id} placeholder="O(n)" value={p.reference_solution.space_complexity} onChange={(e) => setRef({ space_complexity: e.target.value })} />
                  )}
                </Field>
              </div>
              <Field label="Code" hint="Python.">
                {(f) => (
                  <Textarea
                    id={f.id}
                    aria-describedby={f.describedBy}
                    rows={10}
                    spellCheck={false}
                    className="font-mono text-meta"
                    value={p.reference_solution.code}
                    onChange={(e) => setRef({ code: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Explanation" optional hint="For the examiner.">
                {(f) => (
                  <Textarea
                    id={f.id}
                    aria-describedby={f.describedBy}
                    rows={3}
                    value={p.reference_solution.explanation}
                    onChange={(e) => setRef({ explanation: e.target.value })}
                  />
                )}
              </Field>
            </div>
          </Section>

          <Section title="Other accepted solutions" description="Optimal alternatives, and slower approaches that still count as valid.">
            <RowList
              items={p.acceptable_alternatives}
              addLabel="Add an alternative"
              empty="No alternatives."
              make={() => ({ algorithm: '', time_complexity: '', space_complexity: '', description: '' })}
              onChange={(acceptable_alternatives) => update({ acceptable_alternatives })}
              render={(a, set) => (
                <ApproachFields
                  value={a}
                  set={set}
                  extra={
                    <Field label="Why it’s acceptable">
                      {(f) => <Input id={f.id} value={a.description} onChange={(e) => set({ description: e.target.value })} />}
                    </Field>
                  }
                />
              )}
            />
            <h3 className="mb-3 mt-8 text-body font-medium text-ink">Slower but valid</h3>
            <RowList
              items={p.suboptimal_valid}
              addLabel="Add a slower solution"
              empty="None."
              make={() => ({
                algorithm: '',
                time_complexity: '',
                space_complexity: '',
                optimality_gap: '',
                is_acceptable_for_passing: true,
              })}
              onChange={(suboptimal_valid) => update({ suboptimal_valid })}
              render={(s, set) => (
                <ApproachFields
                  value={s}
                  set={set}
                  extra={
                    <>
                      <Field label="Gap to optimal">
                        {(f) => (
                          <Input
                            id={f.id}
                            placeholder="O(n²) vs O(n)"
                            value={s.optimality_gap}
                            onChange={(e) => set({ optimality_gap: e.target.value })}
                          />
                        )}
                      </Field>
                      <Checkbox
                        label="Reaching only this can still pass"
                        checked={s.is_acceptable_for_passing}
                        onChange={(e) => set({ is_acceptable_for_passing: e.target.checked })}
                      />
                    </>
                  }
                />
              )}
            />
          </Section>

          <Section title="Interview guidance" description="What the interviewer looks for and asks about. One item per line.">
            <div className="space-y-4">
              <LinesField label="Concepts to demonstrate" value={p.expected_concepts} onChange={(expected_concepts) => update({ expected_concepts })} />
              <LinesField label="Edge cases" value={p.important_edge_cases} onChange={(important_edge_cases) => update({ important_edge_cases })} />
              <LinesField label="Interview objectives" value={p.interview_objectives} onChange={(interview_objectives) => update({ interview_objectives })} />
              <LinesField label="Follow-up questions" value={p.follow_up_questions} onChange={(follow_up_questions) => update({ follow_up_questions })} />
              <LinesField label="Prompts towards the optimal solution" value={p.optimization_prompts} onChange={(optimization_prompts) => update({ optimization_prompts })} />
            </div>
          </Section>

          <Section title="Tests" description="Visible tests are shown to the candidate; hidden ones only run against their code.">
            <TestList
              label="Visible tests"
              items={p.public_test_cases}
              hidden={false}
              onChange={(public_test_cases) => update({ public_test_cases })}
            />
            <div className="mt-8">
              <TestList
                label="Hidden tests"
                items={p.hidden_test_cases}
                hidden
                onChange={(hidden_test_cases) => update({ hidden_test_cases })}
              />
            </div>
          </Section>

          <Section title="Hints">
            <div className="space-y-4">
              <Checkbox
                label="Hints allowed"
                checked={p.hint_policy.allowed}
                onChange={(e) => setHints({ allowed: e.target.checked })}
              />
              {p.hint_policy.allowed && (
                <>
                  <div className="grid items-end gap-4 sm:grid-cols-2">
                    <Field label="Most hints in one interview">
                      {(f) => (
                        <Input
                          id={f.id}
                          type="number"
                          min={0}
                          max={10}
                          value={p.hint_policy.max_hints}
                          onChange={(e) => setHints({ max_hints: Number(e.target.value) })}
                        />
                      )}
                    </Field>
                    <Field label="Score cost per hint" hint="Percent of the total score.">
                      {(f) => (
                        <Input
                          id={f.id}
                          aria-describedby={f.describedBy}
                          type="number"
                          min={0}
                          max={100}
                          step={1}
                          value={Math.round(p.hint_policy.hint_score_penalty * 100)}
                          onChange={(e) => setHints({ hint_score_penalty: Number(e.target.value) / 100 })}
                        />
                      )}
                    </Field>
                  </div>
                  <Checkbox
                    label="Give hints in order, from gentle to specific"
                    checked={p.hint_policy.progressive}
                    onChange={(e) => setHints({ progressive: e.target.checked })}
                  />
                  <LinesField label="Hints" hint="One per line, in order." value={p.hint_policy.hints} onChange={(hints) => setHints({ hints })} />
                </>
              )}
            </div>
          </Section>

          <Section
            title="Scoring rubric"
            description={`Weights must add up to 100%. Now ${Math.round(rubricTotal * 100)}%.`}
            actions={
              <Button size="sm" variant="ghost" onClick={() => update({ scoring_rubric: { dimensions: DEFAULT_RUBRIC } })}>
                Reset to default
              </Button>
            }
          >
            <div className="divide-y divide-line border-y border-line">
              {p.scoring_rubric.dimensions.map((d, i) => (
                <div key={i} className="flex flex-wrap items-center gap-3 py-2.5">
                  <span className="min-w-0 flex-1 text-body text-ink">{humanize(d.name)}</span>
                  <label className="flex items-center gap-2 text-meta text-muted">
                    <span className="sr-only">{humanize(d.name)} weight in percent</span>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      className="w-20 text-right tabular"
                      value={Math.round(d.weight * 1000) / 10}
                      onChange={(e) => {
                        const dimensions = p.scoring_rubric.dimensions.map((x, j) =>
                          j === i ? { ...x, weight: Number(e.target.value) / 100 } : x,
                        );
                        update({ scoring_rubric: { dimensions } });
                      }}
                    />
                    %
                  </label>
                </div>
              ))}
            </div>
          </Section>
        </div>

        <aside className="min-w-0">
          {!creating && (
            <DefinitionList
              items={[
                { term: 'Added', value: formatDate(p.created_at) },
                { term: 'Added by', value: p.created_by || null },
                { term: 'Invites', value: <span className="tabular">{usage?.invites ?? 0}</span> },
                { term: 'Interviews', value: <span className="tabular">{usage?.interviews ?? 0}</span> },
              ]}
            />
          )}
          <div className="mt-6 flex flex-col gap-2">
            <Button variant="primary" loading={save.isPending} onClick={submit} disabled={!creating && !dirty}>
              {creating ? 'Add problem' : 'Save changes'}
            </Button>
            {dirty && !creating && <p className="text-meta text-muted">Unsaved changes.</p>}
            {!creating && (
              <Button variant="ghostDanger" onClick={() => setConfirmDelete(true)}>
                Delete problem
              </Button>
            )}
          </div>
        </aside>
      </div>

      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={`Delete “${p.title || p.problem_id}”?`}
        actions={
          <>
            <Button onClick={() => setConfirmDelete(false)}>Keep it</Button>
            <Button variant="danger" loading={remove.isPending} onClick={doDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-body text-ink">
          {usage && (usage.invites || usage.interviews)
            ? `It is used by ${usage.invites} invite${usage.invites === 1 ? '' : 's'} and ${usage.interviews} interview${usage.interviews === 1 ? '' : 's'}. Finished interviews keep their results, but waiting invites for it won’t be able to start.`
            : 'No invite or interview uses it.'}{' '}
          This can’t be undone.
        </p>
      </Dialog>
    </>
  );
}

// =============================================================================
// Field groups
// =============================================================================

function LinesField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  // Keep the raw text while typing so blank lines and trailing spaces don't vanish mid-edit
  const [text, setText] = useState(toLines(value));
  useEffect(() => {
    if (fromLines(text).join('\n') !== value.join('\n')) setText(toLines(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <Field label={label} optional hint={hint}>
      {(f) => (
        <Textarea
          id={f.id}
          aria-describedby={f.describedBy}
          rows={Math.min(8, Math.max(3, value.length + 1))}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            onChange(fromLines(e.target.value));
          }}
        />
      )}
    </Field>
  );
}

function RowList<T>({
  items,
  make,
  onChange,
  render,
  addLabel,
  empty,
}: {
  items: T[];
  make: () => T;
  onChange: (items: T[]) => void;
  render: (item: T, set: (patch: Partial<T>) => void) => ReactNode;
  addLabel: string;
  empty: string;
}) {
  return (
    <div>
      {items.length === 0 ? (
        <p className="text-meta text-muted">{empty}</p>
      ) : (
        <ol className="divide-y divide-line border-y border-line">
          {items.map((item, i) => (
            <li key={i} className="flex gap-3 py-4">
              <div className="min-w-0 flex-1 space-y-3">
                {render(item, (patch) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x))))}
              </div>
              <Button
                size="sm"
                variant="ghostDanger"
                aria-label={`Remove item ${i + 1}`}
                icon={<Trash2 className="h-4 w-4" aria-hidden />}
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              />
            </li>
          ))}
        </ol>
      )}
      <Button
        size="sm"
        className="mt-3"
        icon={<Plus className="h-4 w-4" aria-hidden />}
        onClick={() => onChange([...items, make()])}
      >
        {addLabel}
      </Button>
    </div>
  );
}

function ApproachFields<T extends { algorithm: string; time_complexity: string; space_complexity: string }>({
  value,
  set,
  extra,
}: {
  value: T;
  set: (patch: Partial<T>) => void;
  extra?: ReactNode;
}) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Field label="Approach">
          {(f) => <Input id={f.id} value={value.algorithm} onChange={(e) => set({ algorithm: e.target.value } as Partial<T>)} />}
        </Field>
        <Field label="Time">
          {(f) => (
            <Input id={f.id} value={value.time_complexity} onChange={(e) => set({ time_complexity: e.target.value } as Partial<T>)} />
          )}
        </Field>
        <Field label="Space">
          {(f) => (
            <Input id={f.id} value={value.space_complexity} onChange={(e) => set({ space_complexity: e.target.value } as Partial<T>)} />
          )}
        </Field>
      </div>
      {extra}
    </>
  );
}

function TestList({
  label,
  items,
  hidden,
  onChange,
}: {
  label: string;
  items: ProblemTestCase[];
  hidden: boolean;
  onChange: (items: ProblemTestCase[]) => void;
}) {
  return (
    <div>
      <h3 className="mb-3 text-body font-medium text-ink">
        {label} <span className="font-mono text-meta text-muted">{items.length}</span>
      </h3>
      <RowList
        items={items}
        addLabel={hidden ? 'Add a hidden test' : 'Add a visible test'}
        empty="None."
        make={() => ({ input: '', expected_output: '', description: '', is_hidden: hidden })}
        onChange={onChange}
        render={(t, set) => (
          <>
            <Field label="Label" optional>
              {(f) => (
                <Input id={f.id} placeholder="e.g. duplicates" value={t.description ?? ''} onChange={(e) => set({ description: e.target.value })} />
              )}
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Input" hint="The arguments, as the runner expects them.">
                {(f) => (
                  <Textarea
                    id={f.id}
                    aria-describedby={f.describedBy}
                    rows={2}
                    spellCheck={false}
                    className="font-mono text-meta"
                    value={t.input}
                    onChange={(e) => set({ input: e.target.value })}
                  />
                )}
              </Field>
              <Field label="Expected output">
                {(f) => (
                  <Textarea
                    id={f.id}
                    rows={2}
                    spellCheck={false}
                    className="font-mono text-meta"
                    value={t.expected_output}
                    onChange={(e) => set({ expected_output: e.target.value })}
                  />
                )}
              </Field>
            </div>
          </>
        )}
      />
    </div>
  );
}
