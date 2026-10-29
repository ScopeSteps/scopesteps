import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { TextField } from '@/components/TextField';
import { useMemberCommands } from '@/features/identity';
import type { GrantableRole } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { CopyLink } from './CopyLink';
import { RoleCheckboxes } from './RoleCheckboxes';

// Format only: whether the address works is for the email to prove.
const EMAIL_FORMAT = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface InviteMemberModalProps {
  projectId: string;
  onClose: () => void;
}

/**
 * Invites an email with the roles chosen, Viewer unless the approver picks more. The link is
 * emailed by default; once invited it can also be copied to share another way.
 */
export function InviteMemberModal({ projectId, onClose }: InviteMemberModalProps) {
  const [email, setEmail] = useState('');
  const [roles, setRoles] = useState<GrantableRole[]>(['viewer']);
  const [sendEmail, setSendEmail] = useState(true);
  const [problem, setProblem] = useState<{ field: 'email' | 'roles' | null; message: string }>();
  const { invite } = useMemberCommands(projectId);
  const done = invite.data;

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (invite.isPending) {
      return;
    }
    const address = email.trim();
    if (!EMAIL_FORMAT.test(address)) {
      setProblem({ field: 'email', message: 'Enter a valid email address.' });
      return;
    }
    if (roles.length === 0) {
      setProblem({ field: 'roles', message: 'Choose at least one role.' });
      return;
    }
    setProblem(undefined);
    invite.mutate(
      { email: address, roles, send_email: sendEmail },
      {
        onError: (error) => {
          setProblem({ field: null, message: describeError(error) });
        },
      },
    );
  }

  if (done) {
    return (
      <Modal
        title="Invitation ready"
        onClose={onClose}
        footer={
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        }
      >
        <p role="status">
          {done.email_sent
            ? `We emailed an invitation to ${done.invitation.email}.`
            : `${done.invitation.email} is invited. Share the link below privately.`}
        </p>
        {!done.email_sent && sendEmail && (
          <p className="text-[13px] text-warn-ink">
            The email could not be sent. Copy the link and send it another way, or try emailing it
            again from the members list.
          </p>
        )}
        {done.link ? (
          <CopyLink link={done.link} />
        ) : (
          <p className="text-xs text-subtle">
            To share it another way too, use Copy link in the members list; it makes a new link.
          </p>
        )}
      </Modal>
    );
  }

  return (
    <Modal
      title="Invite people"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form="invite-member" variant="primary" disabled={invite.isPending}>
            {invite.isPending ? 'Inviting…' : 'Invite'}
          </Button>
        </>
      }
    >
      <form id="invite-member" noValidate onSubmit={submit} className="flex flex-col gap-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="off"
          inputMode="email"
          value={email}
          onChange={setEmail}
          error={problem?.field === 'email' ? problem.message : null}
          focusOnMount
        />
        <RoleCheckboxes
          value={roles}
          onChange={setRoles}
          error={problem?.field === 'roles' ? problem.message : null}
        />
        <label className="flex cursor-pointer items-center gap-2.5">
          <input
            type="checkbox"
            className="size-4 accent-accent"
            checked={sendEmail}
            onChange={(event) => {
              setSendEmail(event.currentTarget.checked);
            }}
          />
          Email the invitation
        </label>
        <p className="text-xs text-subtle">
          Every invitation has a personal link. It works once, for this email only, and expires in 7
          days.
        </p>
        {problem?.field === null && (
          <p role="alert" className="text-[13px] text-bad-ink">
            {problem.message}
          </p>
        )}
      </form>
    </Modal>
  );
}
