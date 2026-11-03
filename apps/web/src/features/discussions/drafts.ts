import { EMPTY_MENTION_TEXT } from './mentions';
import type { MentionText } from './mentions';

function storageKey(projectId: string, target: string): string {
  return `scopesteps:discussion-draft:${projectId}:${target}`;
}

function isMentionText(value: unknown): value is MentionText {
  return (
    typeof value === 'object' &&
    value !== null &&
    'text' in value &&
    typeof value.text === 'string' &&
    'picked' in value &&
    Array.isArray(value.picked)
  );
}

/**
 * A comment typed but not posted, with the people it mentions, kept for this tab only so closing
 * the panel does not lose it. A convenience: when storage is unavailable the box starts empty.
 */
export function loadDraft(projectId: string, target: string): MentionText {
  try {
    const stored: unknown = JSON.parse(
      window.sessionStorage.getItem(storageKey(projectId, target)) ?? 'null',
    );
    return isMentionText(stored) ? stored : EMPTY_MENTION_TEXT;
  } catch {
    return EMPTY_MENTION_TEXT;
  }
}

export function saveDraft(projectId: string, target: string, value: MentionText): void {
  try {
    if (value.text === '') {
      window.sessionStorage.removeItem(storageKey(projectId, target));
    } else {
      window.sessionStorage.setItem(storageKey(projectId, target), JSON.stringify(value));
    }
  } catch {
    // Storage can be unavailable (private mode, quota); the draft then lasts until reload.
  }
}
