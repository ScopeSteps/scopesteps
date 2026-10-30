function storageKey(projectId: string, target: string): string {
  return `scopesteps:discussion-draft:${projectId}:${target}`;
}

/**
 * A comment typed but not posted, kept for this tab only so closing the panel does not lose it.
 * A convenience: when storage is unavailable the box simply starts empty.
 */
export function loadDraft(projectId: string, target: string): string {
  try {
    return window.sessionStorage.getItem(storageKey(projectId, target)) ?? '';
  } catch {
    return '';
  }
}

export function saveDraft(projectId: string, target: string, text: string): void {
  try {
    if (text === '') {
      window.sessionStorage.removeItem(storageKey(projectId, target));
    } else {
      window.sessionStorage.setItem(storageKey(projectId, target), text);
    }
  } catch {
    // Storage can be unavailable (private mode, quota); the draft then lasts until reload.
  }
}
