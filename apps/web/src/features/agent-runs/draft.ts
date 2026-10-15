function storageKey(projectId: string): string {
  return `scopesteps:chat-draft:${projectId}`;
}

/**
 * The text typed but not sent, kept for this tab only so a reload does not lose it. A
 * convenience: when storage is unavailable the composer simply starts empty.
 */
export function loadDraft(projectId: string): string {
  try {
    return window.sessionStorage.getItem(storageKey(projectId)) ?? '';
  } catch {
    return '';
  }
}

export function saveDraft(projectId: string, text: string): void {
  try {
    if (text === '') {
      window.sessionStorage.removeItem(storageKey(projectId));
    } else {
      window.sessionStorage.setItem(storageKey(projectId), text);
    }
  } catch {
    // Storage can be unavailable (private mode, quota); the draft is then kept until reload.
  }
}
