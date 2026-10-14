import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { attachmentFilename } from './exportFile';
import type { ExportFile, ExportFormat } from './exportFile';

/**
 * The server's export of one version, as text. Read as text rather than parsed, so the preview
 * shows exactly what the server sent.
 */
export function useBacklogExport(projectId: string, versionId: string, format: ExportFormat) {
  return useQuery({
    queryKey: ['backlog', projectId, 'export', versionId, format],
    // Each export is a snapshot stamped with its time: keep the one on screen while the modal
    // is open, and fetch a new one the next time it opens.
    staleTime: Infinity,
    gcTime: 0,
    queryFn: async (): Promise<ExportFile> => {
      const { data, error, response } = await api.GET('/api/v1/backlogs/{version_id}/export', {
        params: { path: { version_id: versionId }, query: { format } },
        parseAs: 'text',
      });
      if (error) {
        throw toApiError(error, response);
      }
      return {
        text: data,
        filename: attachmentFilename(response.headers.get('Content-Disposition')),
        mediaType: response.headers.get('Content-Type') ?? 'text/plain',
      };
    },
  });
}
