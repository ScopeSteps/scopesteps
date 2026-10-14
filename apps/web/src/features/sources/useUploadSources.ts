import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { sourcesQueryKey } from './useSources';

export interface SourceUpload {
  brief: File;
  transcript: File;
  /** Reuse the same key when retrying the same files, so a retry cannot store them twice. */
  idempotencyKey: string;
}

export function useUploadSources(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ brief, transcript, idempotencyKey }: SourceUpload) => {
      const { data, error, response } = await api.POST('/api/v1/projects/{project_id}/sources', {
        params: {
          path: { project_id: projectId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        // The generated contract types binary parts as strings; the files themselves are
        // attached by the serializer below.
        body: { brief: [brief.name], transcript: [transcript.name] },
        bodySerializer: () => {
          const form = new FormData();
          form.append('brief', brief);
          form.append('transcript', transcript);
          return form;
        },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.source_versions;
    },
    // Also after a failure: a 409 means the stored sources are not what this page last saw.
    onSettled: () => queryClient.invalidateQueries({ queryKey: sourcesQueryKey(projectId) }),
  });
}
