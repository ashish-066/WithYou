import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { errorMessage } from '@/lib/api';
import { formatDate } from '@/lib/format';
import type { JobRole } from '@/types';
import {
  Button,
  Checkbox,
  DataTable,
  Dialog,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  StatusLabel,
  Textarea,
  useToast,
  type Column,
} from '@/ui';
import { useDeleteRole, useRoles, useSaveRole } from '../shared/data';

/** "Senior Backend Engineer" → "senior-backend-engineer-k3f9": readable and unique enough. */
function roleIdFrom(title: string): string {
  const slug = title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
  const suffix = Array.from(crypto.getRandomValues(new Uint8Array(3)), (b) => (b % 36).toString(36)).join('');
  return `${slug || 'role'}-${suffix}`;
}

function RoleDrawer({ role, open, onClose }: { role: JobRole | null; open: boolean; onClose: () => void }) {
  const save = useSaveRole();
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [active, setActive] = useState(true);

  useEffect(() => {
    if (!open) return;
    setTitle(role?.role_title ?? '');
    setDescription(role?.job_description ?? '');
    setActive(role?.is_active ?? true);
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, role]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const fields = { role_title: title.trim(), job_description: description.trim(), is_active: active };
    try {
      if (role) await save.mutateAsync({ id: role.role_id, update: fields });
      else await save.mutateAsync({ create: { role_id: roleIdFrom(fields.role_title), ...fields } });
      toast.show(role ? 'Role saved' : `Role “${fields.role_title}” created`);
      onClose();
    } catch {
      // shown under the form
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="lg"
      title={role ? 'Edit role' : 'New job role'}
      description="The interviewer reads the job description to decide which skills to ask about."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="role-form" loading={save.isPending}>
            {role ? 'Save' : 'Create role'}
          </Button>
        </>
      }
    >
      <form id="role-form" onSubmit={submit} className="space-y-5">
        <Field label="Job title">
          {(p) => (
            <Input
              id={p.id}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={200}
              data-autofocus
              placeholder="Senior Backend Engineer"
            />
          )}
        </Field>
        <Field label="Job description" hint="Paste the full posting: responsibilities, required skills, nice-to-haves.">
          {(p) => (
            <Textarea
              id={p.id}
              aria-describedby={p.describedBy}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              maxLength={50_000}
              rows={14}
            />
          )}
        </Field>
        <Checkbox
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          label="Active"
          description="Only active roles can be picked for new invites."
        />
        {role && <p className="font-mono text-meta text-muted">Role id: {role.role_id}</p>}
        {save.error && (
          <p className="text-meta text-bad" role="alert">
            {errorMessage(save.error)}
          </p>
        )}
      </form>
    </Drawer>
  );
}

export function RolesPage() {
  const roles = useRoles();
  const remove = useDeleteRole();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<JobRole | null>(null);
  const [deleting, setDeleting] = useState<JobRole | null>(null);
  const creating = params.get('new') === '1';

  const columns = useMemo<Column<JobRole>[]>(
    () => [
      {
        key: 'title',
        header: 'Role',
        sortValue: (r) => r.role_title.toLowerCase(),
        render: (r) => (
          <div className="min-w-0 max-w-xl">
            <div className="truncate font-medium text-ink">{r.role_title}</div>
            <div className="truncate text-meta text-muted">{r.job_description.slice(0, 140)}</div>
          </div>
        ),
      },
      {
        key: 'status',
        header: 'Status',
        sortValue: (r) => (r.is_active ? 0 : 1),
        render: (r) => (
          <StatusLabel tone={r.is_active ? 'good' : 'neutral'}>{r.is_active ? 'Active' : 'Inactive'}</StatusLabel>
        ),
        hideBelow: 'sm',
      },
      {
        key: 'created',
        header: 'Created',
        numeric: true,
        sortValue: (r) => r.created_at,
        render: (r) => formatDate(r.created_at),
        hideBelow: 'md',
      },
      {
        key: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        render: (r) => (
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>
              Edit
            </Button>
            <Button size="sm" variant="ghostDanger" onClick={() => setDeleting(r)}>
              Delete
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await remove.mutateAsync(deleting.role_id);
      toast.show(`Role “${deleting.role_title}” deleted`);
    } catch (err) {
      toast.show(`Couldn’t delete the role: ${errorMessage(err)}`, 'bad');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Job roles"
        description="Each role holds a job description. Invites for a role get questions about the skills it asks for."
        actions={
          <Button
            variant="primary"
            icon={<Plus className="h-4 w-4" aria-hidden />}
            onClick={() => setParams({ new: '1' }, { replace: true })}
          >
            New role
          </Button>
        }
      />
      {roles.error ? (
        <ErrorState title="Roles didn’t load" error={roles.error} onRetry={() => roles.refetch()} />
      ) : (
        <DataTable
          caption="Job roles"
          columns={columns}
          rows={roles.data ?? []}
          rowKey={(r) => r.role_id}
          loading={roles.isLoading}
          defaultSort={{ key: 'created', dir: 'desc' }}
          pageSize={25}
          empty={
            <EmptyState
              title="No job roles yet"
              body="Add a role with its job description, then pick it when you invite a candidate."
              action={
                <Button variant="primary" onClick={() => setParams({ new: '1' }, { replace: true })}>
                  New role
                </Button>
              }
            />
          }
        />
      )}

      <RoleDrawer
        role={editing}
        open={creating || !!editing}
        onClose={() => {
          setEditing(null);
          if (creating) setParams({}, { replace: true });
        }}
      />

      <Dialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={`Delete “${deleting?.role_title ?? ''}”?`}
        actions={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Keep it
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={confirmDelete}>
              Delete role
            </Button>
          </>
        }
      >
        The role and its job description are removed. Interviews that already used it keep their results. To stop using
        it without deleting, edit it and untick Active.
      </Dialog>
    </>
  );
}
