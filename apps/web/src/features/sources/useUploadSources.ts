import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import type { SourceFile, SourceKind } from './types';
import { sourcesQueryKey } from './useSources';

export interface SourceUpload {
  /** Stored as one command: every file becomes a source, or none does. */
  files: readonly SourceFile[];
  /** Reuse the same key when retrying the same files, so a retry cannot store them twice. */
  idempotencyKey: string;
}

function filenamesOf(files: readonly SourceFile[], kind: SourceKind): string[] | null {
  const names = files.filter((entry) => entry.kind === kind).map((entry) => entry.file.name);
  return names.length > 0 ? names : null;
}

/** Uploads files as new sources, each in a part named by its kind. */
export function useUploadSources(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ files, idempotencyKey }: SourceUpload) => {
      const { data, error, response } = await api.POST('/api/v1/projects/{project_id}/sources', {
        params: {
          path: { project_id: projectId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        // The generated contract types binary parts as strings; the files themselves are
        // attached by the serializer below.
        body: {
          brief: filenamesOf(files, 'brief'),
          transcript: filenamesOf(files, 'transcript'),
          supporting_document: filenamesOf(files, 'supporting_document'),
        },
        bodySerializer: () => {
          const form = new FormData();
          for (const { kind, file } of files) {
            form.append(kind, file);
          }
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
