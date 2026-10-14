export const CHAT_ROUTE = '/projects/:projectId/chat';
export const BACKLOG_ROUTE = '/projects/:projectId/backlog';
export const SOURCES_ROUTE = '/projects/:projectId/sources';

export function chatPath(projectId: string): string {
  return `/projects/${projectId}/chat`;
}

export function backlogPath(projectId: string): string {
  return `/projects/${projectId}/backlog`;
}

export function sourcesPath(projectId: string): string {
  return `/projects/${projectId}/sources`;
}
