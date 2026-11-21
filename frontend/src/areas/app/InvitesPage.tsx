import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { uploadResume } from '@/services/api';
import { Link, useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { errorMessage } from '@/lib/api';
import { formatDateTime, formatRelative, roundLabel } from '@/lib/format';
import type { CandidateInvite, InterviewMode } from '@/types';
import {
  Button,
  ButtonLink,
  Checkbox,
  CopyField,
  DataTable,
  Dialog,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
  StatusLabel,
  Textarea,
  useToast,
  type Column,
  type Tone,
} from '@/ui';
import { useCreateInvite, useDsaProblems, useInviteLink, useInvites, useRevokeInvite, useRoles } from '../shared/data';

const STATUS: Record<CandidateInvite['status'], { word: string; tone: Tone }> = {
  pending: { word: 'Waiting', tone: 'info' },
  used: { word: 'Started', tone: 'good' },
  expired: { word: 'Expired', tone: 'neutral' },
  revoked: { word: 'Withdrawn', tone: 'neutral' },
};

const EXPIRY = [
  { hours: 24, label: '1 day' },
  { hours: 72, label: '3 days' },
  { hours: 168, label: '7 days' },
  { hours: 336, label: '14 days' },
];

interface UploadedDoc {
  name: string;
  text: string;
}

/** Upload a document; its text is read on the server and kept with the invite. */
function DocumentField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: UploadedDoc | null;
  onChange: (doc: UploadedDoc | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadResume(file);
      onChange({ name: file.name, text: result.resume_text });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The file couldn’t be read');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Field label={label} optional hint={hint} error={error}>
      {(p) =>
        value ? (
          <div className="flex items-center justify-between gap-3 border border-line px-3 py-2">
            <span className="min-w-0 truncate text-body text-ink">
              {value.name}
              <span className="ml-2 text-meta text-muted">{value.text.length.toLocaleString()} characters read</span>
            </span>
            <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
              Remove
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <input
              id={p.id}
              aria-describedby={p.describedBy}
              type="file"
              accept=".pdf,image/*"
              disabled={busy}
              onChange={(e) => {
                pick(e.target.files?.[0]);
                e.target.value = '';
              }}
              className="text-meta text-muted file:mr-3 file:rounded-ui file:border file:border-line-strong file:bg-surface file:px-3 file:py-1.5 file:text-meta file:text-ink"
            />
            {busy && <Spinner label="Reading" />}
          </div>
        )
      }
    </Field>
  );
}

function NewInviteDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const roles = useRoles();
  const [mode, setMode] = useState<InterviewMode>('round1');
  const problems = useDsaProblems(open && mode === 'round2_dsa');
  const create = useCreateInvite();
  const toast = useToast();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [roleId, setRoleId] = useState('');
  const [problemId, setProblemId] = useState('');
  const [hours, setHours] = useState(72);
  const [requireApp, setRequireApp] = useState(false);
  const [link, setLink] = useState<{ url: string; name: string } | null>(null);
  const [github, setGithub] = useState('');
  const [linkedin, setLinkedin] = useState('');
  const [otherLinks, setOtherLinks] = useState('');
  const [resume, setResume] = useState<UploadedDoc | null>(null);
  const [linkedinDoc, setLinkedinDoc] = useState<UploadedDoc | null>(null);

  const activeRoles = (roles.data ?? []).filter((r) => r.is_active);

  useEffect(() => {
    if (!problemId && problems.data?.length) setProblemId(problems.data[0].problem_id);
  }, [problems.data, problemId]);

  const reset = () => {
    setName('');
    setEmail('');
    setGithub('');
    setLinkedin('');
    setOtherLinks('');
    setResume(null);
    setLinkedinDoc(null);
    setLink(null);
    create.reset();
  };

  const close = () => {
    reset();
    onClose();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const invite = await create.mutateAsync({
        candidate_name: name.trim(),
        candidate_email: email.trim() || undefined,
        role_id: roleId || undefined,
        interview_mode: mode,
        dsa_problem_id: mode === 'round2_dsa' ? problemId || undefined : undefined,
        require_secure_app: requireApp,
        expires_in_hours: hours,
        github_url: github.trim() || undefined,
        linkedin_url: linkedin.trim() || undefined,
        other_links: otherLinks
          .split(/\s+/)
          .map((x) => x.trim())
          .filter(Boolean)
          .slice(0, 10),
        resume_text: resume?.text,
        linkedin_text: linkedinDoc?.text,
      });
      setLink({ url: `${window.location.origin}${invite.path}`, name: name.trim() });
      toast.show(`Invite created for ${name.trim()}`);
    } catch {
      // shown under the form
    }
  };

  if (link) {
    return (
      <Drawer
        open={open}
        onClose={close}
        title="Link ready"
        description={`Send this link to ${link.name}. It works once.`}
        footer={
          <>
            <Button variant="ghost" onClick={reset}>
              Create another
            </Button>
            <Button variant="primary" onClick={close}>
              Done
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <CopyField label="Interview link" value={link.url} />
          <p className="text-meta text-muted">
            Copy it now: for security, the full link is shown only here. If it gets lost, create a new invite.
          </p>
        </div>
      </Drawer>
    );
  }

  return (
    <Drawer
      open={open}
      onClose={close}
      title="New invite"
      description="A single-use link that starts one interview."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="new-invite" loading={create.isPending}>
            Create link
          </Button>
        </>
      }
    >
      <form id="new-invite" onSubmit={submit} className="space-y-5">
        <Field label="Candidate name">
          {(p) => (
            <Input
              id={p.id}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={120}
              data-autofocus
            />
          )}
        </Field>
        <Field label="Candidate email" optional hint="For your records. Presence View doesn’t email candidates yet.">
          {(p) => (
            <Input
              id={p.id}
              aria-describedby={p.describedBy}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>
        <Field
          label="Job role"
          optional
          hint={
            activeRoles.length === 0 && !roles.isLoading ? (
              <>
                No roles yet.{' '}
                <Link to="/app/roles?new=1" className="text-accent underline underline-offset-2">
                  Add one
                </Link>{' '}
                so questions follow the job description.
              </>
            ) : (
              'Questions follow the role’s job description.'
            )
          }
        >
          {(p) => (
            <Select
              id={p.id}
              aria-describedby={p.describedBy}
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
            >
              <option value="">No specific role</option>
              {activeRoles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_title}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Round">
          {(p) => (
            <Select id={p.id} value={mode} onChange={(e) => setMode(e.target.value as InterviewMode)}>
              <option value="round1">Round 1: technical conversation</option>
              <option value="round2_dsa">Round 2: coding</option>
            </Select>
          )}
        </Field>
        {mode === 'round2_dsa' && (
          <Field label="Coding problem" error={problems.error ? errorMessage(problems.error) : null}>
            {(p) => (
              <Select
                id={p.id}
                invalid={p.invalid}
                aria-describedby={p.describedBy}
                value={problemId}
                onChange={(e) => setProblemId(e.target.value)}
                required
              >
                {problems.isLoading && <option value="">Loading problems…</option>}
                {problems.data?.map((pr) => (
                  <option key={pr.problem_id} value={pr.problem_id}>
                    {pr.title} ({pr.difficulty})
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        <fieldset className="space-y-4 border-t border-line pt-5">
          <legend className="text-body font-medium text-ink">Candidate background</legend>
          <p className="-mt-2 text-meta text-muted">
            The interviewer asks about these and checks what the candidate says against them. The candidate isn’t
            asked for them again.
          </p>
          <DocumentField
            label="Resume"
            hint="PDF or image. The text is read now; the file isn’t kept."
            value={resume}
            onChange={setResume}
          />
          <Field label="GitHub" optional>
            {(p) => (
              <Input
                id={p.id}
                placeholder="https://github.com/username"
                value={github}
                onChange={(e) => setGithub(e.target.value)}
                maxLength={500}
              />
            )}
          </Field>
          <Field label="LinkedIn" optional hint="LinkedIn can’t be read automatically; add the PDF export below to use it.">
            {(p) => (
              <Input
                id={p.id}
                aria-describedby={p.describedBy}
                placeholder="https://linkedin.com/in/username"
                value={linkedin}
                onChange={(e) => setLinkedin(e.target.value)}
                maxLength={500}
              />
            )}
          </Field>
          <DocumentField
            label="LinkedIn profile export"
            hint="On the profile: More, then Save to PDF."
            value={linkedinDoc}
            onChange={setLinkedinDoc}
          />
          <Field label="Other links" optional hint="Portfolio, personal site, blog, project pages. One per line, up to 10.">
            {(p) => (
              <Textarea
                id={p.id}
                aria-describedby={p.describedBy}
                rows={3}
                placeholder={'https://janedoe.dev\nhttps://kaggle.com/janedoe'}
                value={otherLinks}
                onChange={(e) => setOtherLinks(e.target.value)}
              />
            )}
          </Field>
        </fieldset>
        <Field label="Link valid for">
          {(p) => (
            <Select id={p.id} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              {EXPIRY.map((x) => (
                <option key={x.hours} value={x.hours}>
                  {x.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Checkbox
          checked={requireApp}
          onChange={(e) => setRequireApp(e.target.checked)}
          label="Require the locked app"
          description="The candidate must use the Presence View desktop app; the browser won’t start the interview. Only tick this if they can install it."
        />
        {create.error && (
          <p className="text-meta text-bad" role="alert">
            {errorMessage(create.error)}
          </p>
        )}
      </form>
    </Drawer>
  );
}

export function InvitesPage() {
  const invites = useInvites();
  const [params, setParams] = useSearchParams();
  const drawerOpen = params.get('new') === '1';
  const setDrawer = (open: boolean) => setParams(open ? { new: '1' } : {}, { replace: true });
  const revoke = useRevokeInvite();
  const link = useInviteLink();
  const toast = useToast();
  const [revoking, setRevoking] = useState<CandidateInvite | null>(null);
  const [copying, setCopying] = useState<{ name: string; url?: string; error?: string } | null>(null);

  const showLink = async (invite: CandidateInvite) => {
    setCopying({ name: invite.candidate_name });
    try {
      const { path } = await link.mutateAsync(invite.invite_id);
      setCopying({ name: invite.candidate_name, url: `${window.location.origin}${path}` });
    } catch (err) {
      setCopying({ name: invite.candidate_name, error: errorMessage(err) });
    }
  };

  const columns = useMemo<Column<CandidateInvite>[]>(
    () => [
      {
        key: 'candidate',
        header: 'Candidate',
        sortValue: (i) => i.candidate_name.toLowerCase(),
        render: (i) => (
          <div className="min-w-0">
            <div className="truncate font-medium text-ink">{i.candidate_name}</div>
            {i.candidate_email && <div className="truncate text-meta text-muted">{i.candidate_email}</div>}
          </div>
        ),
      },
      {
        key: 'role',
        header: 'Role',
        sortValue: (i) => i.role_title || null,
        render: (i) => i.role_title || <span className="text-muted">—</span>,
        hideBelow: 'md',
      },
      {
        key: 'background',
        header: 'Background',
        hideBelow: 'lg',
        render: (i) => {
          const b = i.background;
          const parts = [
            b?.has_resume && 'Resume',
            b?.github_url && 'GitHub',
            b?.has_linkedin_export ? 'LinkedIn' : b?.linkedin_url ? 'LinkedIn link only' : null,
            b?.other_links?.length && `${b.other_links.length} link${b.other_links.length === 1 ? '' : 's'}`,
          ].filter(Boolean);
          return parts.length ? <span className="text-meta">{parts.join(', ')}</span> : <span className="text-muted">None</span>;
        },
      },
      {
        key: 'round',
        header: 'Round',
        render: (i) => (
          <span>
            {roundLabel(i.interview_mode)}
            {i.require_secure_app && <span className="block text-meta text-muted">Locked app</span>}
          </span>
        ),
        hideBelow: 'sm',
      },
      {
        key: 'status',
        header: 'Status',
        sortValue: (i) => i.status,
        render: (i) => <StatusLabel tone={STATUS[i.status].tone}>{STATUS[i.status].word}</StatusLabel>,
      },
      {
        key: 'expires',
        header: 'Expires',
        numeric: true,
        sortValue: (i) => i.expires_at,
        render: (i) =>
          i.status === 'pending' ? (
            <span title={formatDateTime(i.expires_at)}>{formatRelative(i.expires_at)}</span>
          ) : (
            <span className="text-muted">—</span>
          ),
        hideBelow: 'md',
      },
      {
        key: 'created',
        header: 'Created',
        numeric: true,
        sortValue: (i) => i.created_at,
        render: (i) => formatDateTime(i.created_at),
        hideBelow: 'lg',
      },
      {
        key: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        render: (i) =>
          i.session_id ? (
            <Link
              to={`/app/interviews/${encodeURIComponent(i.session_id)}`}
              className="text-meta font-medium text-accent underline-offset-2 hover:underline"
            >
              Open interview
            </Link>
          ) : i.status === 'pending' ? (
            <div className="flex justify-end gap-1">
              <Button size="sm" variant="ghost" onClick={() => showLink(i)}>
                Copy link
              </Button>
              <Button size="sm" variant="ghostDanger" onClick={() => setRevoking(i)}>
                Withdraw
              </Button>
            </div>
          ) : null,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const confirmRevoke = async () => {
    if (!revoking) return;
    try {
      await revoke.mutateAsync(revoking.invite_id);
      toast.show(`Invite for ${revoking.candidate_name} withdrawn`);
    } catch (err) {
      toast.show(`Couldn’t withdraw the invite: ${errorMessage(err)}`, 'bad');
    } finally {
      setRevoking(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Invites"
        description="Each link works once and expires. Send it to a candidate to start their interview."
        actions={
          <>
            <ButtonLink to="/interview">Try it yourself</ButtonLink>
            <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setDrawer(true)}>
              New invite
            </Button>
          </>
        }
      />
      {invites.error ? (
        <ErrorState title="Invites didn’t load" error={invites.error} onRetry={() => invites.refetch()} />
      ) : (
        <DataTable
          caption="Invites"
          columns={columns}
          rows={invites.data ?? []}
          rowKey={(i) => i.invite_id}
          loading={invites.isLoading}
          defaultSort={{ key: 'created', dir: 'desc' }}
          pageSize={25}
          empty={
            <EmptyState
              title="No invites yet"
              body="An invite is a single-use link. The candidate opens it, checks their camera and microphone, and the interview starts."
              action={
                <Button variant="primary" onClick={() => setDrawer(true)}>
                  New invite
                </Button>
              }
            />
          }
        />
      )}
      <NewInviteDrawer open={drawerOpen} onClose={() => setDrawer(false)} />

      <Dialog
        open={!!revoking}
        onClose={() => setRevoking(null)}
        title={`Withdraw ${revoking?.candidate_name ?? ''}’s invite?`}
        actions={
          <>
            <Button variant="ghost" onClick={() => setRevoking(null)}>
              Keep it
            </Button>
            <Button variant="danger" loading={revoke.isPending} onClick={confirmRevoke}>
              Withdraw
            </Button>
          </>
        }
      >
        The link stops working right away. If the candidate opens it, they’re told it was withdrawn. You can send them a
        new invite later.
      </Dialog>

      <Dialog
        open={!!copying}
        onClose={() => setCopying(null)}
        title={`Link for ${copying?.name ?? ''}`}
        actions={
          <Button variant="primary" onClick={() => setCopying(null)}>
            Done
          </Button>
        }
      >
        <div className="mt-2 space-y-2">
          {copying?.url ? (
            <CopyField label="Interview link" value={copying.url} />
          ) : copying?.error ? (
            <p className="text-bad" role="alert">
              {copying.error}
            </p>
          ) : (
            <p>Getting the link…</p>
          )}
          <p className="text-meta">Still single use: it stops working once the interview starts.</p>
        </div>
      </Dialog>
    </>
  );
}
