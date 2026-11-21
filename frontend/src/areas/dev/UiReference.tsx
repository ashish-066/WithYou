/**
 * Every building block in one place, in both palettes. Development only:
 * the route exists only when `import.meta.env.DEV` is true (see App.tsx).
 */
import { useState } from 'react';
import {
  Activity,
  Building2,
  FileCode2,
  Inbox,
  ListChecks,
  Mail,
  Plus,
  ScrollText,
  Settings,
  Trophy,
  Users,
  Workflow,
} from 'lucide-react';
import {
  AppShell,
  Button,
  Checkbox,
  CopyField,
  DataTable,
  DefinitionList,
  Dialog,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Pagination,
  Section,
  Select,
  Spinner,
  StatusLabel,
  Tabs,
  Textarea,
  useToast,
  type Area,
  type Column,
  type NavGroup,
  type Tone,
} from '@/ui';

interface SampleInterview {
  id: string;
  candidate: string;
  role: string;
  round: 'Technical' | 'Coding';
  status: { word: string; tone: Tone };
  started: string;
  minutes: number | null;
  score: number | null;
}

const SAMPLE: SampleInterview[] = [
  {
    id: 'session-71a9e3650802',
    candidate: 'Meera Iyer',
    role: 'Backend Engineer',
    round: 'Technical',
    status: { word: 'Completed', tone: 'good' },
    started: '2026-11-13 16:45',
    minutes: 5,
    score: 72,
  },
  {
    id: 'session-0c41aa21b7e9',
    candidate: 'Daniel Okafor',
    role: 'Backend Engineer',
    round: 'Coding',
    status: { word: 'In progress', tone: 'live' },
    started: '2026-11-14 09:12',
    minutes: null,
    score: null,
  },
  {
    id: 'session-9be2d0f3c118',
    candidate: 'Lena Fischer',
    role: 'Data Engineer',
    round: 'Technical',
    status: { word: 'Ended early', tone: 'warn' },
    started: '2026-11-12 14:03',
    minutes: 3,
    score: 41,
  },
  {
    id: 'session-55d7e1a04c2b',
    candidate: 'Arjun Rao',
    role: 'Platform Engineer',
    round: 'Coding',
    status: { word: 'Flagged', tone: 'bad' },
    started: '2026-11-11 11:30',
    minutes: 38,
    score: 64,
  },
  {
    id: 'inv-120703c4ef264754',
    candidate: 'Sofia Marquez',
    role: 'Data Engineer',
    round: 'Technical',
    status: { word: 'Invited', tone: 'neutral' },
    started: '',
    minutes: null,
    score: null,
  },
];

const columns: Column<SampleInterview>[] = [
  {
    key: 'candidate',
    header: 'Candidate',
    sortValue: (r) => r.candidate,
    render: (r) => (
      <div>
        <div className="font-medium text-ink">{r.candidate}</div>
        <div className="font-mono text-[12px] text-muted">{r.id.slice(0, 16)}</div>
      </div>
    ),
  },
  { key: 'role', header: 'Role', sortValue: (r) => r.role, render: (r) => r.role, hideBelow: 'md' },
  { key: 'round', header: 'Round', render: (r) => r.round, hideBelow: 'sm' },
  {
    key: 'status',
    header: 'Status',
    sortValue: (r) => r.status.word,
    render: (r) => <StatusLabel tone={r.status.tone}>{r.status.word}</StatusLabel>,
  },
  {
    key: 'started',
    header: 'Started',
    sortValue: (r) => r.started || null,
    numeric: true,
    render: (r) => r.started || '—',
    hideBelow: 'lg',
  },
  {
    key: 'minutes',
    header: 'Length',
    align: 'right',
    numeric: true,
    sortValue: (r) => r.minutes,
    render: (r) => (r.minutes != null ? `${r.minutes} min` : '—'),
    hideBelow: 'md',
  },
  {
    key: 'score',
    header: 'Score',
    align: 'right',
    numeric: true,
    sortValue: (r) => r.score,
    render: (r) => (r.score != null ? r.score : '—'),
  },
];

const APP_NAV: NavGroup[] = [
  {
    items: [
      { to: '/app/_ui', label: 'Interviews', icon: <ListChecks />, end: true },
      { to: '/app/_ui/invites', label: 'Invites', icon: <Mail /> },
      { to: '/app/_ui/roles', label: 'Job roles', icon: <Inbox /> },
      { to: '/app/_ui/rankings', label: 'Rankings', icon: <Trophy /> },
    ],
  },
  {
    label: 'Organization',
    items: [
      { to: '/app/_ui/team', label: 'Team', icon: <Users /> },
      { to: '/app/_ui/settings', label: 'Settings', icon: <Settings /> },
    ],
  },
];

const PLATFORM_NAV: NavGroup[] = [
  {
    items: [
      { to: '/app/_ui', label: 'Health', icon: <Activity />, end: true },
      { to: '/app/_ui/orgs', label: 'Organizations', icon: <Building2 /> },
      { to: '/app/_ui/interviews', label: 'All interviews', icon: <ListChecks /> },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/app/_ui/workers', label: 'Workers & queues', icon: <Workflow /> },
      { to: '/app/_ui/problems', label: 'Problem library', icon: <FileCode2 /> },
      { to: '/app/_ui/audit', label: 'Audit log', icon: <ScrollText /> },
    ],
  },
];

const SWATCHES = ['canvas', 'surface', 'sunken', 'line', 'ink', 'muted', 'accent', 'good', 'warn', 'bad'] as const;
const swatchClass: Record<(typeof SWATCHES)[number], string> = {
  canvas: 'bg-canvas',
  surface: 'bg-surface',
  sunken: 'bg-sunken',
  line: 'bg-line',
  ink: 'bg-ink',
  muted: 'bg-muted',
  accent: 'bg-accent',
  good: 'bg-good',
  warn: 'bg-warn',
  bad: 'bg-bad',
};

type TabKey = 'summary' | 'transcript' | 'coding' | 'integrity';

export function UiReference() {
  const [area, setArea] = useState<Area>('app');
  const [tab, setTab] = useState<TabKey>('summary');
  const [page, setPage] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  return (
    <AppShell
      area={area}
      areaName={area === 'app' ? 'Presence View' : 'Platform'}
      nav={area === 'app' ? APP_NAV : PLATFORM_NAV}
      user={{
        name: 'Ashish Vardhan Karanam',
        email: 'ashi…@gmail.com',
        detail: area === 'app' ? 'Org admin' : 'Platform admin',
      }}
      onSignOut={() => toast.show('Sign out is disabled on the reference page', 'warn')}
      switchTo={{ to: '/app/_ui', label: area === 'app' ? 'Platform' : 'Workspace' }}
    >
      <PageHeader
        title="Interface reference"
        description="Every building block of the new dashboard, in the palette of the area you pick. Development only."
        actions={
          <>
            <Select aria-label="Area" value={area} onChange={(e) => setArea(e.target.value as Area)} className="w-48">
              <option value="app">Organization workspace</option>
              <option value="platform">Platform console</option>
            </Select>
            <Button
              variant="primary"
              icon={<Plus className="h-4 w-4" aria-hidden />}
              onClick={() => setDrawerOpen(true)}
            >
              New invite
            </Button>
          </>
        }
        meta={
          <>
            <span>Newsreader · Instrument Sans · JetBrains Mono</span>
            <StatusLabel tone="live">Live</StatusLabel>
          </>
        }
      />

      <Section title="Type" description="Six sizes: 40, 28, 20, 16, 14, 13.">
        <div className="space-y-3 border-y border-line py-5">
          <p className="font-display text-h1 text-ink">Meera Iyer</p>
          <p className="font-display text-h2 text-ink">Backend Engineer, technical round</p>
          <p className="font-display text-h3 text-ink">Strong on distributed systems, thin on testing</p>
          <p className="max-w-2xl font-display text-lead leading-relaxed text-ink">
            The candidate explained consistent hashing clearly and adjusted their design when asked about node failure,
            but could not describe how they would test the rebalancing logic.
          </p>
          <p className="text-body text-ink">Interface text: tables, forms, buttons and navigation.</p>
          <p className="text-meta text-muted">Secondary text: hints, captions, timestamps.</p>
          <p className="font-mono text-meta tabular text-ink">session-71a9e3650802 · 16:45:57 · 72 / 100</p>
        </div>
      </Section>

      <Section
        title="Colour"
        description="Text colours pass WCAG AA on every surface. Switch the area above to see the console palette."
      >
        <ul className="flex flex-wrap gap-x-6 gap-y-3 border-y border-line py-4">
          {SWATCHES.map((s) => (
            <li key={s} className="flex items-center gap-2">
              <span className={`h-5 w-5 border border-line-strong ${swatchClass[s]}`} aria-hidden />
              <span className="font-mono text-meta text-muted">{s}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Status" description="Always a word. The mark differs by shape too, so it reads without colour.">
        <div className="flex flex-wrap gap-x-6 gap-y-2 border-y border-line py-4">
          <StatusLabel tone="good">Completed</StatusLabel>
          <StatusLabel tone="live">In progress</StatusLabel>
          <StatusLabel tone="warn">Ended early</StatusLabel>
          <StatusLabel tone="bad">Flagged</StatusLabel>
          <StatusLabel tone="info">Report pending</StatusLabel>
          <StatusLabel tone="neutral">Invited</StatusLabel>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-2 border-y border-line py-4">
          <Button variant="primary">Create invite</Button>
          <Button>Copy link</Button>
          <Button variant="ghost">Cancel</Button>
          <Button variant="danger" onClick={() => setDialogOpen(true)}>
            Revoke
          </Button>
          <Button variant="primary" loading>
            Saving
          </Button>
          <Button size="sm">Small</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Section>

      <Section
        title="Table"
        description="Click a column to sort. Rows are links; narrow windows drop the less important columns."
        actions={
          <Button size="sm" variant="ghost" onClick={() => setLoading((l) => !l)}>
            {loading ? 'Show rows' : 'Show loading'}
          </Button>
        }
      >
        <DataTable
          caption="Sample interviews"
          columns={columns}
          rows={loading ? [] : SAMPLE}
          loading={loading}
          rowKey={(r) => r.id}
          rowHref={() => '/app/_ui'}
          defaultSort={{ key: 'started', dir: 'desc' }}
        />
        <Pagination page={page} pageSize={5} total={23} onPage={setPage} />
      </Section>

      <Section title="Tabs">
        <Tabs
          label="Report sections"
          value={tab}
          onChange={setTab}
          items={[
            { key: 'summary', label: 'Summary' },
            { key: 'transcript', label: 'Transcript', count: 24 },
            { key: 'coding', label: 'Coding' },
            { key: 'integrity', label: 'Integrity', count: 2 },
          ]}
        />
        <p className="py-4 text-body text-muted">Showing: {tab}</p>
      </Section>

      <Section
        title="Main column and side column"
        description="Detail pages: the report on the left, facts on the right. The side column drops below on narrow windows."
      >
        <div className="flex flex-col gap-8 border-y border-line py-5 lg:flex-row">
          <div className="min-w-0 flex-1 space-y-3">
            <p className="font-display text-h3 text-ink">Summary</p>
            <p className="max-w-prose font-display text-lead leading-relaxed text-ink">
              Clear communicator with solid backend fundamentals. Explained caching trade-offs well. Struggled to
              estimate the cost of the proposed design at scale.
            </p>
          </div>
          <aside className="w-full shrink-0 lg:w-[300px]">
            <DefinitionList
              items={[
                { term: 'Started', value: <span className="font-mono text-meta">13 Nov, 16:45</span> },
                { term: 'Length', value: '5 min 25 s' },
                { term: 'Sent by', value: 'Ashish' },
                { term: 'Taken in', value: 'Browser' },
                { term: 'Recording', value: null },
              ]}
            />
          </aside>
        </div>
      </Section>

      <Section title="Forms">
        <div className="max-w-lg space-y-4 border-y border-line py-5">
          <Field label="Candidate name">
            {(p) => <Input id={p.id} aria-describedby={p.describedBy} defaultValue="Meera Iyer" />}
          </Field>
          <Field label="Candidate email" optional hint="We don’t email them yet; this is for your records.">
            {(p) => <Input id={p.id} type="email" aria-describedby={p.describedBy} placeholder="name@example.com" />}
          </Field>
          <Field label="Round" error="Pick a coding problem for the coding round.">
            {(p) => (
              <Select id={p.id} invalid={p.invalid} aria-describedby={p.describedBy} defaultValue="coding">
                <option value="technical">Round 1: technical conversation</option>
                <option value="coding">Round 2: coding</option>
              </Select>
            )}
          </Field>
          <Field label="Job description">
            {(p) => <Textarea id={p.id} aria-describedby={p.describedBy} rows={3} />}
          </Field>
          <Checkbox
            label="Require the locked app"
            description="The candidate can’t take this interview in a browser."
          />
          <Field label="Interview link">
            {() => (
              <CopyField
                label="Interview link"
                value="https://presence-view.duckdns.org/interview?invite=eyJhbGciOi…"
              />
            )}
          </Field>
          <Field label="One-time password">
            {() => <CopyField label="One-time password" value="vT4m-82qc-LxWp" mask />}
          </Field>
        </div>
      </Section>

      <Section title="States">
        <div className="space-y-4">
          <EmptyState
            title="No interviews yet"
            body="Invite a candidate and their interview shows up here as soon as they start."
            action={<Button variant="primary">New invite</Button>}
          />
          <ErrorState
            title="Interviews didn’t load"
            error={new Error('Can’t reach the server. Check your connection.')}
            onRetry={() => toast.show('Retried')}
          />
          <Spinner label="Loading the report" />
        </div>
      </Section>

      <Section title="Overlays">
        <div className="flex flex-wrap gap-2 border-y border-line py-4">
          <Button onClick={() => setDrawerOpen(true)}>Open drawer</Button>
          <Button onClick={() => setDialogOpen(true)}>Open dialog</Button>
          <Button onClick={() => toast.show('Invite revoked')}>Show toast</Button>
          <Button onClick={() => toast.show('Couldn’t revoke the invite: it was already used.', 'bad')}>
            Show error toast
          </Button>
        </div>
      </Section>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Revoke this invite?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              Keep it
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setDialogOpen(false);
                toast.show('Invite revoked');
              }}
            >
              Revoke
            </Button>
          </>
        }
      >
        Meera Iyer’s link stops working right away. You can send a new one later.
      </Dialog>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="New invite"
        description="Each link works once and expires."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDrawerOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => setDrawerOpen(false)}>
              Create link
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Candidate name">{(p) => <Input id={p.id} data-autofocus />}</Field>
          <Field label="Job role">
            {(p) => (
              <Select id={p.id}>
                <option>Backend Engineer</option>
                <option>Data Engineer</option>
              </Select>
            )}
          </Field>
        </div>
      </Drawer>
    </AppShell>
  );
}
