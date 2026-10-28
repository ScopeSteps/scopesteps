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
  /** The project's Change requests page, with the given request in view when there is one. */
  changeRequestHref: (changeRequestId: string | null) => string;
  onStartNewRun: () => void;
  /** Whether the reader may approve; a candidate's decisions are answered by an approver. */
  canApprove: boolean;
  /** The approved baseline a suggested change request is made on, as this page shows it. */
  baseline: { versionId: string; contentHash: string } | null;
  /** The project's current sources, which a suggested draft run pins. */
  sourceVersionIds: readonly string[];
  /** Shows a run a suggestion started. */
  onRunStarted: (runId: string) => void;
  /** The newest message in the thread, so only the latest failure offers a new run. */
  latestId: string | null;
}
