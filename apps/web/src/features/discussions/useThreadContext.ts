import { useVersionHistory, versionName } from '@/features/backlog';
import { useCurrentUser } from '@/features/identity';

/** What every thread card needs to know about the person reading and the project's versions. */
export function useThreadContext(projectId: string) {
  const { data: user } = useCurrentUser();
  const { data: versions } = useVersionHistory(projectId);
  const roles =
    user?.memberships.filter((m) => m.project_id === projectId).map((m) => m.role) ?? [];

  function versionLabel(versionId: string | null): string | null {
    const version = versionId === null ? undefined : versions?.find((v) => v.id === versionId);
    if (!version) {
      return null;
    }
    switch (version.state) {
      case 'approved':
        return `about ${versionName(version.number)}`;
      case 'in_review':
        return 'about a candidate in review';
      case 'draft':
      case 'rejected':
        return 'about a draft';
    }
  }

  return {
    user,
    resolvesAny: roles.includes('editor') || roles.includes('approver'),
    versionLabel,
  };
}
