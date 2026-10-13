function storageKey(projectId: string): string {
  return `scopesteps:last-run:${projectId}`;
}

/**
 * Remembers the project's most recent run in this browser, so the backlog page can offer it
 * again. A convenience only: the run itself lives on the server and its URL always works.
 */
export function rememberRun(projectId: string, runId: string): void {
  try {
    window.localStorage.setItem(storageKey(projectId), runId);
  } catch {
    // Storage can be unavailable (private mode, quota); the run URL still restores the run.
  }
}

export function lastRunId(projectId: string): string | null {
  try {
    return window.localStorage.getItem(storageKey(projectId));
  } catch {
    return null;
  }
}
