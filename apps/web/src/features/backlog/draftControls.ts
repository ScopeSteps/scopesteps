import { isStale } from './types';
import type { DraftCommands } from './useDraftCommands';

/** What a reader may do to a draft, and the commands that do it. Absent on a read-only version. */
export interface DraftControls {
  commands: DraftCommands;
  canEdit: boolean;
  canAnswer: boolean;
  /** Whether agent suggestions can be accepted or rejected: by editing a draft, or once each by
   * an approver on a change candidate. */
  canReviewSuggestions: boolean;
}

/** Whether a row's controls are unavailable: a command is in flight, or the page is stale. */
export function isLocked(draft: DraftControls): boolean {
  return draft.commands.isPending || isStale(draft.commands.error);
}

/** The error the row that sent the last command should show; a stale page is reported above. */
export function errorFor(draft: DraftControls, target: string): Error | null {
  const { error } = draft.commands;
  return draft.commands.target === target && error && !isStale(error) ? error : null;
}

export function isSaving(draft: DraftControls, target: string): boolean {
  return draft.commands.isPending && draft.commands.target === target;
}
