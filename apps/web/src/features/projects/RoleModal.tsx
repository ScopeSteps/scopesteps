import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { isGrantableRole, useMemberCommands } from '@/features/identity';
import type { GrantableRole, ProjectMember } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { RoleChoice } from './RoleChoice';
import { MY_WORK_KEY } from './useMyWork';
import { projectQueryKey } from './useProject';
import { PROJECT_LIST_KEY } from './useProjects';

interface RoleModalProps {
  projectId: string;
  member: ProjectMember;
  onClose: () => void;
}

/**
 * Changes a member's role at the revision on screen. The server keeps at least one approver and
 * explains when the change would leave none.
 */
export function RoleModal({ projectId, member, onClose }: RoleModalProps) {
  const [role, setRole] = useState<GrantableRole>(
    isGrantableRole(member.role) ? member.role : 'viewer',
  );
  const { changeRole } = useMemberCommands(projectId);
  const queryClient = useQueryClient();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    changeRole.mutate(
      { userId: member.user_id, role, expectedRevision: member.revision },
      {
        onSuccess: () => {
          // Changing your own role changes what this app shows you on the project.
          void Promise.all([
            queryClient.invalidateQueries({ queryKey: projectQueryKey(projectId) }),
            queryClient.invalidateQueries({ queryKey: PROJECT_LIST_KEY }),
            queryClient.invalidateQueries({ queryKey: MY_WORK_KEY }),
          ]);
          onClose();
        },
      },
    );
  }

  return (
    <Modal
      title={`Role of ${member.display_name}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            form="member-role"
            variant="primary"
            disabled={changeRole.isPending || role === member.role}
          >
            {changeRole.isPending ? 'Saving…' : 'Save role'}
          </Button>
        </>
      }
    >
      <form id="member-role" noValidate onSubmit={submit} className="flex flex-col gap-3">
        <RoleChoice value={role} onChange={setRole} />
        {changeRole.error && (
          <p role="alert" className="text-[13px] text-bad-ink">
            {describeError(changeRole.error)}
          </p>
        )}
      </form>
    </Modal>
  );
}
