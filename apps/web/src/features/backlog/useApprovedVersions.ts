import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import type { VersionPage, VersionSummary } from './types';

const PAGE_LIMIT = 100;

async function versionPage(projectId: string, cursor: string | null): Promise<VersionPage> {
  const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/backlogs', {
    params: { path: { project_id: projectId }, query: { limit: PAGE_LIMIT, cursor } },
  });
  if (error) {
    throw toApiError(error, response);
  }
  return data;
}

/** Every approved version of the project, newest first, read through all pages of the history. */
export function useApprovedVersions(projectId: string) {
  return useQuery({
    queryKey: ['backlog', projectId, 'versions', 'approved'],
    queryFn: async () => {
      const approved: VersionSummary[] = [];
      let cursor: string | null = null;
      do {
        const page = await versionPage(projectId, cursor);
        approved.push(...page.versions.filter((version) => version.state === 'approved'));
        cursor = page.next_cursor;
      } while (cursor !== null);
      return approved;
    },
  });
}
