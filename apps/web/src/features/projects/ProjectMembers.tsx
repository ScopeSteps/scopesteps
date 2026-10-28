import type { components } from '@scopesteps/api-client';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { Tag } from '@/components/Tag';
import {
  CURRENT_USER_KEY,
  GRANTABLE_ROLES,
  useCanApprove,
  useCurrentUser,
  useInvitations,
  useMemberCommands,
  useProjectMembers,
} from '@/features/identity';
import type { Invitation, ProjectMember } from '@/features/identity';
import { describeError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

import { CopyLink } from './CopyLink';
import { InviteMemberModal } from './InviteMemberModal';
import { RolesModal } from './RolesModal';
import { PROJECT_LIST_KEY } from './useProjects';

type ProjectSummary = components['schemas']['ProjectResponse'];

interface ProjectMembersProps {
  projectId: string;
  /** After leaving the project: the app goes home, where it is no longer listed. */
  onLeft: () => void;
}

type Dialog =
  | { kind: 'invite' }
  | { kind: 'roles'; member: ProjectMember }
  | { kind: 'remove'; member: ProjectMember }
  | { kind: 'leave' }
  | { kind: 'link'; invitation: Invitation };

function RoleTags({ roles }: { roles: readonly string[] }) {
  const shown = GRANTABLE_ROLES.filter(({ role }) => roles.includes(role));
  return (
    <span className="flex flex-wrap justify-end gap-1">
      {shown.map(({ role, label }) => (
        <Tag key={role} tone={role === 'approver' ? 'accent' : 'neutral'}>
          {label}
        </Tag>
      ))}
    </span>
  );
}

/**
 * Who has which roles in the project, by the names they gave. An approver also invites people,
 * changes roles, removes members and manages pending invitations; everyone may leave. The
 * server decides every action: the panel only hides what the role can never do.
 */
export function ProjectMembers({ projectId, onLeft }: ProjectMembersProps) {
  const { data: members, error, isPending, refetch } = useProjectMembers(projectId);
  const { data: me } = useCurrentUser();
  const isApprover = useCanApprove(projectId);
  const invitations = useInvitations(projectId, isApprover);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => {
    setDialog(null);
  };

  return (
    <section aria-labelledby="project-members-heading" className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <h3 id="project-members-heading" className="text-[13px] font-semibold">
          Members
        </h3>
        {isApprover && (
          <Button
            size="sm"
            onClick={() => {
              setDialog({ kind: 'invite' });
            }}
          >
            Invite people
          </Button>
        )}
      </div>
      {isPending && (
        <p role="status" className="text-xs text-subtle">
          Loading members…
        </p>
      )}
      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-bad-ink">
          Could not load the members. {describeError(error)}
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
      )}
      {members && members.length > 0 && (
        <ul aria-label="Members" className="m-0 flex list-none flex-col gap-1 p-0">
          {members.map((member) => {
            const isMe = member.user_id === me?.id;
            return (
              <li
                key={member.user_id}
                className="flex flex-wrap items-center gap-x-2.5 gap-y-1 py-1"
              >
                <Avatar name={member.display_name} size={28} />
                <span className="flex min-w-36 flex-1 flex-col leading-tight">
                  <span className="truncate font-medium">
                    {member.display_name}
                    {isMe && <span className="text-subtle"> (you)</span>}
                  </span>
                  {member.job_title && (
                    <span className="truncate text-xs text-subtle">{member.job_title}</span>
                  )}
                </span>
                <RoleTags roles={member.roles} />
                {(isApprover || isMe) && (
                  <span className="flex gap-1">
                    {isApprover && (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Change roles of ${member.display_name}`}
                        onClick={() => {
                          setDialog({ kind: 'roles', member });
                        }}
                      >
                        Roles
                      </Button>
                    )}
                    {isMe ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setDialog({ kind: 'leave' });
                        }}
                      >
                        Leave project
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove ${member.display_name}`}
                        onClick={() => {
                          setDialog({ kind: 'remove', member });
                        }}
                      >
                        Remove
                      </Button>
                    )}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {isApprover && (
        <PendingInvitations
          projectId={projectId}
          invitations={invitations.data ?? []}
          error={invitations.error}
          onCopy={(invitation) => {
            setDialog({ kind: 'link', invitation });
          }}
        />
      )}
      {dialog?.kind === 'invite' && <InviteMemberModal projectId={projectId} onClose={close} />}
      {dialog?.kind === 'roles' && (
        <RolesModal projectId={projectId} member={dialog.member} onClose={close} />
      )}
      {dialog?.kind === 'remove' && (
        <RemoveModal projectId={projectId} member={dialog.member} onClose={close} />
      )}
      {dialog?.kind === 'leave' && me && (
        <LeaveModal projectId={projectId} userId={me.id} onClose={close} onLeft={onLeft} />
      )}
      {dialog?.kind === 'link' && (
        <NewLinkModal projectId={projectId} invitation={dialog.invitation} onClose={close} />
      )}
    </section>
  );
}

function PendingInvitations({
  projectId,
  invitations,
  error,
  onCopy,
}: {
  projectId: string;
  invitations: readonly Invitation[];
  error: Error | null;
  onCopy: (invitation: Invitation) => void;
}) {
  const { emailInvitation, cancel } = useMemberCommands(projectId);
  const failure = emailInvitation.error ?? cancel.error;
  if (error) {
    return (
      <p role="alert" className="text-xs text-bad-ink">
        Could not load the invitations. {describeError(error)}
      </p>
    );
  }
  if (invitations.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-1">
      <h4 className="text-xs font-semibold text-muted">Invited</h4>
      <ul aria-label="Pending invitations" className="m-0 flex list-none flex-col gap-1 p-0">
        {invitations.map((invitation) => (
          <li
            key={invitation.id}
            className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-lg border border-line px-2.5 py-1.5"
          >
            <span className="flex min-w-44 flex-1 flex-col leading-tight">
              <span className="font-medium break-all">{invitation.email}</span>
              <span className="text-xs text-subtle">
                {invitation.expired ? (
                  'Expired: make a new link to use it'
                ) : (
                  <>
                    Expires{' '}
                    <time dateTime={invitation.expires_at}>
                      {formatWhen(invitation.expires_at)}
                    </time>
                  </>
                )}
              </span>
            </span>
            <Tag tone={invitation.expired ? 'bad' : 'warn'}>
              {invitation.expired ? 'Expired' : 'Pending'}
            </Tag>
            <RoleTags roles={invitation.roles} />
            <span className="flex flex-wrap gap-1">
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Copy a new link for ${invitation.email}`}
                onClick={() => {
                  onCopy(invitation);
                }}
              >
                Copy link
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Email the invitation to ${invitation.email} again`}
                disabled={emailInvitation.isPending}
                onClick={() => {
                  emailInvitation.mutate(invitation.id);
                }}
              >
                Resend email
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Cancel the invitation for ${invitation.email}`}
                disabled={cancel.isPending}
                onClick={() => {
                  cancel.mutate(invitation.id);
                }}
              >
                Cancel
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {emailInvitation.isSuccess && (
        <p role="status" className="text-xs text-ok-ink">
          Invitation emailed to {emailInvitation.data.email}.
        </p>
      )}
      {failure && (
        <p role="alert" className="text-xs text-bad-ink">
          {describeError(failure)}
        </p>
      )}
    </div>
  );
}

function NewLinkModal({
  projectId,
  invitation,
  onClose,
}: {
  projectId: string;
  invitation: Invitation;
  onClose: () => void;
}) {
  const { newLink } = useMemberCommands(projectId);
  const link = newLink.data?.link;
  return (
    <Modal
      title={`Link for ${invitation.email}`}
      onClose={onClose}
      footer={
        link ? (
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        ) : (
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button
              variant="primary"
              disabled={newLink.isPending}
              onClick={() => {
                newLink.mutate(invitation.id);
              }}
            >
              {newLink.isPending ? 'Making a link…' : 'Make a new link'}
            </Button>
          </>
        )
      }
    >
      {link ? (
        <CopyLink link={link} />
      ) : (
        <p>
          A new link replaces the one sent before, which stops working. It works once, for{' '}
          {invitation.email} only, and expires in 7 days. Share it privately.
        </p>
      )}
      {newLink.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(newLink.error)}
        </p>
      )}
    </Modal>
  );
}

function RemoveModal({
  projectId,
  member,
  onClose,
}: {
  projectId: string;
  member: ProjectMember;
  onClose: () => void;
}) {
  const { remove } = useMemberCommands(projectId);
  return (
    <Modal
      title={`Remove ${member.display_name}?`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate(member.user_id, { onSuccess: onClose });
            }}
          >
            {remove.isPending ? 'Removing…' : 'Remove'}
          </Button>
        </>
      }
    >
      <p>
        {member.display_name} loses access to this project now. Their past work stays, with their
        name.
      </p>
      {remove.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(remove.error)}
        </p>
      )}
    </Modal>
  );
}

function LeaveModal({
  projectId,
  userId,
  onClose,
  onLeft,
}: {
  projectId: string;
  userId: string;
  onClose: () => void;
  onLeft: () => void;
}) {
  const { remove } = useMemberCommands(projectId);
  const queryClient = useQueryClient();
  return (
    <Modal
      title="Leave this project?"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Stay</Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate(userId, {
                onSuccess: () => {
                  // Home opens a project that is alone in the cached list, so the one just left
                  // goes from the cache before the list is read again.
                  queryClient.setQueryData<ProjectSummary[]>(PROJECT_LIST_KEY, (projects) =>
                    projects?.filter((project) => project.id !== projectId),
                  );
                  void Promise.all([
                    queryClient.invalidateQueries({ queryKey: CURRENT_USER_KEY }),
                    queryClient.invalidateQueries({ queryKey: PROJECT_LIST_KEY }),
                  ]).then(onLeft);
                },
              });
            }}
          >
            {remove.isPending ? 'Leaving…' : 'Leave project'}
          </Button>
        </>
      }
    >
      <p>
        You lose access to this project now. Your past work stays, with your name. An approver can
        invite you again.
      </p>
      {remove.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(remove.error)}
        </p>
      )}
    </Modal>
  );
}
