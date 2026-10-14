import { queryOptions, useQuery } from '@tanstack/react-query';

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

function historyQuery(projectId: string) {
  return queryOptions({
    queryKey: ['backlog', projectId, 'versions'],
    queryFn: async () => {
      const versions: VersionSummary[] = [];
      let cursor: string | null = null;
      do {
        const page = await versionPage(projectId, cursor);
        versions.push(...page.versions);
        cursor = page.next_cursor;
      } while (cursor !== null);
      return versions;
    },
  });
}

function approvedOnly(versions: VersionSummary[]): VersionSummary[] {
  return versions.filter((version) => version.state === 'approved');
}

/**
 * Every version of the project, drafts and rejections included, newest first, read through all
 * pages of the history. Nothing is requested while `enabled` is false.
 */
export function useVersionHistory(projectId: string, enabled = true) {
  return useQuery({ ...historyQuery(projectId), enabled });
}

/** Every approved version of the project, newest first, from the same history. */
export function useApprovedVersions(projectId: string) {
  return useQuery({ ...historyQuery(projectId), select: approvedOnly });
}
