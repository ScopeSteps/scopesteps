import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function sourceVersionsQueryKey(projectId: string, sourceId: string) {
  return ['sources', projectId, 'versions', sourceId] as const;
}

/** Every version of one current source, newest first. Disabled until a source is known. */
export function useSourceVersions(projectId: string, sourceId: string | null) {
  return useQuery({
    queryKey: sourceVersionsQueryKey(projectId, sourceId ?? 'none'),
    enabled: sourceId !== null,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/sources/{source_id}/versions',
        { params: { path: { project_id: projectId, source_id: sourceId ?? '' } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data.source_versions;
    },
  });
}

export interface NewSourceVersion {
  sourceId: string;
  file: File;
  /** Reuse the same key when retrying the same file, so a retry cannot store it twice. */
  idempotencyKey: string;
}

/**
 * Stores a file as a source's next version. The API answers with the current version unchanged
 * when the file is the same as it.
 */
export function useAddSourceVersion(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ sourceId, file, idempotencyKey }: NewSourceVersion) => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/sources/{source_id}/versions',
        {
          params: {
            path: { project_id: projectId, source_id: sourceId },
            header: { 'Idempotency-Key': idempotencyKey },
          },
          // The generated contract types the binary part as a string; the file itself is
          // attached by the serializer below.
          body: { file: file.name },
          bodySerializer: () => {
            const form = new FormData();
            form.append('file', file);
            return form;
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A new transcript version can bring new speakers, and the project's word count moves.
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['sources', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['projects', projectId] }),
      ]),
  });
}
