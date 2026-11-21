import { useMemo, useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { errorMessage } from '@/lib/api';
import type { AuthUser } from '@/types';
import {
  Button,
  CopyField,
  DataTable,
  Dialog,
  Drawer,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  useToast,
  type Column,
} from '@/ui';
import { useAddUser, useChangeRole, useRemoveMember, useResetPassword, useUsers } from '../shared/data';

function AddMemberDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const add = useAddUser();
  const toast = useToast();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'recruiter'>('recruiter');
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);

  const close = () => {
    setName('');
    setEmail('');
    setRole('recruiter');
    setCreated(null);
    add.reset();
    onClose();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      // The server generates the one-time password and returns it this once
      const user = await add.mutateAsync({ name: name.trim(), email: email.trim(), role });
      setCreated({ email: user.email, password: user.one_time_password });
      toast.show(`${user.name} added`);
    } catch {
      // shown under the form
    }
  };

  if (created) {
    return (
      <Drawer
        open={open}
        onClose={close}
        title="Member added"
        description="Send them these sign-in details through a private channel."
        footer={
          <Button variant="primary" onClick={close}>
            Done
          </Button>
        }
      >
        <div className="space-y-5">
          <Field label="Email">{() => <CopyField label="Email" value={created.email} />}</Field>
          <Field label="Password">{() => <CopyField label="Password" value={created.password} mask />}</Field>
          <p className="text-meta text-muted">
            This password is shown only once. Presence View doesn’t email it, and members can’t change it yet.
          </p>
        </div>
      </Drawer>
    );
  }

  return (
    <Drawer
      open={open}
      onClose={close}
      title="Add a member"
      description="They can invite candidates and see your organization’s interviews."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="member-form" loading={add.isPending}>
            Add member
          </Button>
        </>
      }
    >
      <form id="member-form" onSubmit={submit} className="space-y-5">
        <Field label="Name">
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
        <Field label="Email">
          {(p) => <Input id={p.id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
        </Field>
        <Field label="Access" hint="Admins can also add members.">
          {(p) => (
            <Select
              id={p.id}
              aria-describedby={p.describedBy}
              value={role}
              onChange={(e) => setRole(e.target.value as 'admin' | 'recruiter')}
            >
              <option value="recruiter">Recruiter</option>
              <option value="admin">Admin</option>
            </Select>
          )}
        </Field>
        <p className="text-meta text-muted">A one-time password is generated when you add them.</p>
        {add.error && (
          <p className="text-meta text-bad" role="alert">
            {errorMessage(add.error)}
          </p>
        )}
      </form>
    </Drawer>
  );
}

type MemberAction = { kind: 'role' | 'reset' | 'remove'; member: AuthUser };

/** Confirm, then do: change access, reset the password (and show the new one once), or remove. */
function MemberActionDialog({ action, onClose }: { action: MemberAction | null; onClose: () => void }) {
  const changeRole = useChangeRole();
  const reset = useResetPassword();
  const remove = useRemoveMember();
  const toast = useToast();
  const [newPassword, setNewPassword] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setNewPassword(null);
    setError(null);
    onClose();
  };

  if (!action) return null;
  const { kind, member } = action;
  const busy = changeRole.isPending || reset.isPending || remove.isPending;
  const toRole = member.role === 'admin' ? 'recruiter' : 'admin';

  const run = async () => {
    setError(null);
    try {
      if (kind === 'role') {
        await changeRole.mutateAsync({ userId: member.user_id, role: toRole });
        toast.show(`${member.name} is now ${toRole === 'admin' ? 'an admin' : 'a recruiter'}`);
        close();
      } else if (kind === 'reset') {
        setNewPassword((await reset.mutateAsync(member.user_id)).one_time_password);
      } else {
        await remove.mutateAsync(member.user_id);
        toast.show(`${member.name} removed`);
        close();
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  if (newPassword) {
    return (
      <Dialog
        open
        onClose={close}
        title={`New password for ${member.name}`}
        actions={
          <Button variant="primary" onClick={close}>
            Done
          </Button>
        }
      >
        <div className="mt-2 space-y-2">
          <CopyField label="New password" value={newPassword} mask />
          <p className="text-meta">
            Shown only once. Send it to them privately. Their old password no longer works, but devices where they’re
            already signed in stay signed in.
          </p>
        </div>
      </Dialog>
    );
  }

  const copy = {
    role: {
      title: toRole === 'admin' ? `Make ${member.name} an admin?` : `Make ${member.name} a recruiter?`,
      body:
        toRole === 'admin'
          ? 'Admins can also add, change and remove team members.'
          : 'They keep inviting candidates and seeing results, but can no longer manage the team.',
      confirm: toRole === 'admin' ? 'Make admin' : 'Make recruiter',
    },
    reset: {
      title: `Reset ${member.name}’s password?`,
      body: 'Their current password stops working. You’ll get a new one-time password to send them.',
      confirm: 'Reset password',
    },
    remove: {
      title: `Remove ${member.name}?`,
      body: 'They’re signed out right away and can’t sign in again. Invites and interviews they created stay with the organization.',
      confirm: 'Remove',
    },
  }[kind];

  return (
    <Dialog
      open
      onClose={close}
      title={copy.title}
      actions={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant={kind === 'role' ? 'primary' : 'danger'} loading={busy} onClick={run}>
            {copy.confirm}
          </Button>
        </>
      }
    >
      {copy.body}
      {error && (
        <p className="mt-3 text-bad" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

export function TeamPage() {
  const { user } = useAuth();
  const users = useUsers();
  const [adding, setAdding] = useState(false);
  const [action, setAction] = useState<MemberAction | null>(null);

  const columns = useMemo<Column<AuthUser>[]>(
    () => [
      {
        key: 'name',
        header: 'Name',
        sortValue: (u) => u.name.toLowerCase(),
        render: (u) => (
          <span className="font-medium text-ink">
            {u.name}
            {u.user_id === user?.user_id && <span className="ml-2 text-meta font-normal text-muted">You</span>}
          </span>
        ),
      },
      { key: 'email', header: 'Email', sortValue: (u) => u.email, render: (u) => u.email, hideBelow: 'sm' },
      {
        key: 'role',
        header: 'Access',
        sortValue: (u) => u.role,
        render: (u) => (u.role === 'admin' ? 'Admin' : 'Recruiter'),
      },
      {
        key: 'actions',
        header: <span className="sr-only">Actions</span>,
        align: 'right',
        render: (u) =>
          u.user_id === user?.user_id ? null : (
            <div className="flex justify-end gap-1">
              <Button size="sm" variant="ghost" onClick={() => setAction({ kind: 'role', member: u })}>
                {u.role === 'admin' ? 'Make recruiter' : 'Make admin'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAction({ kind: 'reset', member: u })}>
                Reset password
              </Button>
              <Button size="sm" variant="ghostDanger" onClick={() => setAction({ kind: 'remove', member: u })}>
                Remove
              </Button>
            </div>
          ),
      },
    ],
    [user?.user_id],
  );

  return (
    <>
      <PageHeader
        title="Team"
        description={`People in ${user?.org_name || 'your organization'} who can invite candidates and see results.`}
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setAdding(true)}>
            Add member
          </Button>
        }
      />
      {users.error ? (
        <ErrorState title="The team didn’t load" error={users.error} onRetry={() => users.refetch()} />
      ) : (
        <DataTable
          caption="Team members"
          columns={columns}
          rows={users.data ?? []}
          rowKey={(u) => u.user_id}
          loading={users.isLoading}
          defaultSort={{ key: 'name', dir: 'asc' }}
        />
      )}
      <AddMemberDrawer open={adding} onClose={() => setAdding(false)} />
      <MemberActionDialog action={action} onClose={() => setAction(null)} />
    </>
  );
}
