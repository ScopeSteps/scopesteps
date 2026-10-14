export const CHAT_ROUTE = '/projects/:projectId/chat';
export const BACKLOG_ROUTE = '/projects/:projectId/backlog';
export const CHANGES_ROUTE = '/projects/:projectId/changes';
export const SOURCES_ROUTE = '/projects/:projectId/sources';
export const ACTIVITY_ROUTE = '/projects/:projectId/activity';

export function chatPath(projectId: string): string {
  return `/projects/${projectId}/chat`;
}

export function backlogPath(projectId: string): string {
  return `/projects/${projectId}/backlog`;
}

export function sourcesPath(projectId: string): string {
  return `/projects/${projectId}/sources`;
}

export function activityPath(projectId: string): string {
  return `/projects/${projectId}/activity`;
}

export function changesPath(projectId: string): string {
  return `/projects/${projectId}/changes`;
}
