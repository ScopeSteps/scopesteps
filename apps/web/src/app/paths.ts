export const BACKLOG_ROUTE = '/projects/:projectId/backlog';
export const SOURCES_ROUTE = '/projects/:projectId/sources';
export const ACTIVITY_ROUTE = '/projects/:projectId/activity';

export function backlogPath(projectId: string): string {
  return `/projects/${projectId}/backlog`;
}

export function sourcesPath(projectId: string): string {
  return `/projects/${projectId}/sources`;
}

export function activityPath(projectId: string): string {
  return `/projects/${projectId}/activity`;
}
