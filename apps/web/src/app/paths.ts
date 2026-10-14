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

const PROJECT_PAGE = /^\/projects\/[^/]+\/([^/]+)/;

/**
 * The same page in another project, or its chat when the page belongs to no project. The query
 * string is dropped: the run or version it names belongs to the project being left.
 */
export function switchProjectPath(pathname: string, projectId: string): string {
  const page = PROJECT_PAGE.exec(pathname)?.[1];
  return page ? `/projects/${projectId}/${page}` : chatPath(projectId);
}
