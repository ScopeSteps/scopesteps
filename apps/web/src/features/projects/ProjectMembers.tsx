import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Tag } from '@/components/Tag';
import { roleLabelFor, useProjectMembers } from '@/features/identity';
import { describeError } from '@/lib/apiError';

interface ProjectMembersProps {
  projectId: string;
}

/**
 * Who has a role in the project, by the names they gave in their profile. The API lists
 * members but cannot invite people or change roles yet, so neither is offered.
 */
export function ProjectMembers({ projectId }: ProjectMembersProps) {
  const { data: members, error, isPending, refetch } = useProjectMembers(projectId);

  return (
    <section aria-labelledby="project-members-heading" className="flex flex-col gap-1.5">
      <h3 id="project-members-heading" className="text-[13px] font-semibold">
        Members
      </h3>
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
      {members?.length === 0 && (
        <p className="text-xs text-subtle">Nobody has a role in this project yet.</p>
      )}
      {members && members.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {members.map((member) => {
            const role = roleLabelFor(member.roles);
            return (
              <li key={member.user_id} className="flex items-center gap-2.5 py-1">
                <Avatar name={member.display_name} size={28} />
                <span className="flex min-w-0 flex-1 flex-col leading-tight">
                  <span className="truncate font-medium">{member.display_name}</span>
                  {member.job_title && (
                    <span className="truncate text-xs text-subtle">{member.job_title}</span>
                  )}
                </span>
                {role && <Tag>{role}</Tag>}
              </li>
            );
          })}
        </ul>
      )}
      <span className="text-xs text-subtle">
        Inviting people and changing roles are not available yet.
      </span>
    </section>
  );
}
