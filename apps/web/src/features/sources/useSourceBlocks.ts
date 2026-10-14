import { useQueries, useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

function blocksQuery(projectId: string, sourceVersionId: string) {
  return {
    queryKey: ['sources', projectId, 'blocks', sourceVersionId],
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/sources/{source_version_id}/blocks',
        { params: { path: { project_id: projectId, source_version_id: sourceVersionId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A source version is immutable, so its blocks never go stale.
    staleTime: Infinity,
  };
}

export function useSourceBlocks(projectId: string, sourceVersionId: string) {
  return useQuery(blocksQuery(projectId, sourceVersionId));
}

export type BlockSource =
  | { status: 'pending' }
  | { status: 'error'; error: Error; retry: () => void }
  | { status: 'found'; sourceVersionId: string }
  | { status: 'missing' };

/**
 * Which of the given source versions holds a block. The agent cites blocks by id alone, and
 * the run pins the versions it read, so the block is looked up among those.
 */
export function useBlockSource(
  projectId: string,
  sourceVersionIds: readonly string[],
  blockId: string,
): BlockSource {
  const results = useQueries({
    queries: sourceVersionIds.map((id) => blocksQuery(projectId, id)),
  });
  const index = results.findIndex((result) => result.data?.some((block) => block.id === blockId));
  const sourceVersionId = sourceVersionIds[index];
  if (sourceVersionId !== undefined) {
    return { status: 'found', sourceVersionId };
  }
  const failed = results.find((result) => result.error !== null);
  if (failed?.error) {
    return {
      status: 'error',
      error: failed.error,
      retry: () => {
        for (const result of results) {
          void result.refetch();
        }
      },
    };
  }
  return results.some((result) => result.isPending) ? { status: 'pending' } : { status: 'missing' };
}
