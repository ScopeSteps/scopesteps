import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { attachmentFilename } from './exportFile';
import type { ExportFile } from './exportFile';

/**
 * The server's Jira CSV of one version, as text. Kept as the server sent it, so the preview is
 * built from the same text the download saves.
 */
export function useBacklogExport(projectId: string, versionId: string) {
  return useQuery({
    queryKey: ['backlog', projectId, 'export', versionId, 'csv'],
    // Keep the file on screen while the modal is open, so the preview and the download never
    // differ, and fetch it again the next time it opens.
    staleTime: Infinity,
    gcTime: 0,
    queryFn: async (): Promise<ExportFile> => {
      const { data, error, response } = await api.GET('/api/v1/backlogs/{version_id}/export', {
        params: { path: { version_id: versionId }, query: { format: 'csv' } },
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
