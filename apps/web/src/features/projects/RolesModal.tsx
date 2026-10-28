import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { useMemberCommands } from '@/features/identity';
import type { GrantableRole, ProjectMember } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { RoleCheckboxes } from './RoleCheckboxes';

const GRANTABLE: readonly string[] = ['viewer', 'editor', 'approver'];

function grantable(roles: readonly string[]): GrantableRole[] {
  return roles.filter((role): role is GrantableRole => GRANTABLE.includes(role));
}

interface RolesModalProps {
  projectId: string;
  member: ProjectMember;
  onClose: () => void;
}

/** Changes a member's roles at the revision on screen; at least one role stays. */
export function RolesModal({ projectId, member, onClose }: RolesModalProps) {
  const [roles, setRoles] = useState<GrantableRole[]>(grantable(member.roles));
  const [problem, setProblem] = useState<string | null>(null);
  const { changeRoles } = useMemberCommands(projectId);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (roles.length === 0) {
      setProblem('Choose at least one role.');
      return;
    }
    setProblem(null);
    changeRoles.mutate(
      { userId: member.user_id, roles, expectedRevision: member.revision },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal
      title={`Roles of ${member.display_name}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            form="member-roles"
            variant="primary"
            disabled={changeRoles.isPending}
          >
            {changeRoles.isPending ? 'Saving…' : 'Save roles'}
          </Button>
        </>
      }
    >
      <form id="member-roles" noValidate onSubmit={submit} className="flex flex-col gap-3">
        <RoleCheckboxes value={roles} onChange={setRoles} error={problem} />
        {changeRoles.error && (
          <p role="alert" className="text-[13px] text-bad-ink">
            {describeError(changeRoles.error)}
          </p>
        )}
      </form>
    </Modal>
  );
}
