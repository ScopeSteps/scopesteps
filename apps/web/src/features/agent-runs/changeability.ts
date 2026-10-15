import type { ThreadContext } from './threadContext';
import type { Question, Run } from './types';

/**
 * An answer can change while its round is open, or once its draft is saved and still undecided.
 * Approving or rejecting that version locks it (ADR 0010).
 */
export function changeability(
  run: Run,
  question: Question,
  context: Pick<ThreadContext, 'canEdit' | 'scope'>,
): { canChange: boolean; lockedNote: string | null } {
  if (question.status === 'open' || !context.canEdit) {
    return { canChange: false, lockedNote: null };
  }
  if (run.status === 'waiting_for_input') {
    return { canChange: true, lockedNote: null };
  }
  if (run.status !== 'ready_for_review' || run.candidate_version_id === null) {
    return { canChange: false, lockedNote: null };
  }
  if (context.scope?.open_version_id === run.candidate_version_id) {
    return { canChange: true, lockedNote: null };
  }
  return {
    canChange: false,
    lockedNote:
      context.scope?.baseline_version_id === run.candidate_version_id
        ? 'Locked: the version that uses this answer is approved.'
        : 'Locked: the version that used this answer was approved or rejected.',
  };
}
