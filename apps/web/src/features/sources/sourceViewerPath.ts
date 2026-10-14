/** The Sources page with one source version open in the viewer, scrolled to a paragraph. */
export function sourceViewerPath(projectId: string, sourceVersionId: string, blockId?: string) {
  const search = new URLSearchParams({ version: sourceVersionId });
  if (blockId) {
    search.set('block', blockId);
  }
  return `/projects/${projectId}/sources?${search.toString()}`;
}
