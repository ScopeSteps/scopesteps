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

export const SIGN_IN_ROUTE = '/sign-in';

const RETURN_PARAM = 'next';
// Only for parsing: a return path must resolve to this origin to be followed.
const PARSE_ORIGIN = 'https://scopesteps.invalid';

/** The sign-in page, remembering the page to return to afterwards. */
export function signInPath(returnTo?: string): string {
  if (returnTo === undefined || safeReturnPath(returnTo) === '/') {
    return SIGN_IN_ROUTE;
  }
  return `${SIGN_IN_ROUTE}?${new URLSearchParams({ [RETURN_PARAM]: returnTo }).toString()}`;
}

export function returnPathParam(search: URLSearchParams): string {
  return safeReturnPath(search.get(RETURN_PARAM));
}

/**
 * A path in this app, or `/` for anything else, so a crafted sign-in link cannot send the user
 * to another site (`//evil.example`, `https://…`) or back to sign-in.
 */
export function safeReturnPath(raw: string | null): string {
  if (raw?.startsWith('/') !== true) {
    return '/';
  }
  let url: URL;
  try {
    url = new URL(raw, PARSE_ORIGIN);
  } catch {
    return '/';
  }
  if (url.origin !== PARSE_ORIGIN || url.pathname === SIGN_IN_ROUTE) {
    return '/';
  }
  return `${url.pathname}${url.search}${url.hash}`;
}
