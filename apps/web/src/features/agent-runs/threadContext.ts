import type { components } from '@scopesteps/api-client';

import type { EvidenceRef } from './types';

type ScopeStatus = components['schemas']['ScopeStatusResponse'];

/** What every message in the thread needs from the page around it. */
export interface ThreadContext {
  projectId: string;
  canEdit: boolean;
  /** The project's baseline and open version, to tell whether an answer is still changeable. */
  scope: ScopeStatus | undefined;
  answeringId: string | null;
  onAnswer: (runId: string, questionId: string) => void;
  onShowEvidence: (ref: EvidenceRef) => void;
  backlogHref: (versionId: string) => string;
  /** The project's Change requests page. */
  changesHref: string;
  onStartNewRun: () => void;
  /** The newest message in the thread, so only the latest failure offers a new run. */
  latestId: string | null;
}
