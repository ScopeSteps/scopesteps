export const BACKLOG_ROUTE = '/projects/:projectId/backlog';
export const SOURCES_ROUTE = '/projects/:projectId/sources';

export function backlogPath(projectId: string): string {
  return `/projects/${projectId}/backlog`;
}

export function sourcesPath(projectId: string): string {
  return `/projects/${projectId}/sources`;
}
