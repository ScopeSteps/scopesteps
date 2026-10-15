import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';
import { roleLabelFor } from '@/features/identity';

type Schemas = components['schemas'];
type Run = Schemas['RunResponse'];
type BacklogVersion = Schemas['BacklogVersionResponse'];
type Membership = Schemas['MembershipResponse'];
type ScopeStatus = Schemas['ScopeStatusResponse'];

/**
 * What the shell shows about a project. Every value is presentation derived from API data:
 * the server stays the judge of ids, states, blockers and permissions.
 */
export interface ProjectStatus {
  projectId: string;
  roleLabel: string | null;
  chip: StatusChip | null;
  nextStep: NextStep | null;
  /** The questions in the chat that wait for an answer. */
  chatAttention: number;
  /** What still blocks approval of the draft on the backlog page. */
  backlogAttention: number;
  /** The people whose decision rights no source states and nobody has confirmed. */
  peopleAttention: number;
  chatPath: string;
  backlogPath: string;
  changesPath: string;
  sourcesPath: string;
  peoplePath: string;
  /** The run the chat page shows, for the run details in the top bar. */
  runInView: Run | null;
  activityPath: string;
}

export interface StatusChip {
  text: string;
  tone: TagTone;
}

export interface NextStep {
  label: string;
  /** Where the step is done. Without it the pill only informs. */
  to?: string;
  working?: boolean;
}

const VIEWER_LABEL = 'Viewer';

export function roleLabel(memberships: readonly Membership[], projectId: string): string | null {
  return roleLabelFor(
    memberships
      .filter((membership) => membership.project_id === projectId)
      .map((membership) => membership.role),
  );
}

function plural(count: number, noun: string): string {
  return `${String(count)} ${noun}${count === 1 ? '' : 's'}`;
}

function openQuestions(run: Run): number {
  return run.status === 'waiting_for_input'
    ? run.questions.filter((question) => question.status === 'open').length
    : 0;
}

function isUnderReview(version: BacklogVersion): boolean {
  return version.state === 'draft' || version.state === 'in_review';
}

export function chatAttention(run: Run | undefined): number {
  return run ? openQuestions(run) : 0;
}

export function backlogAttention(version: BacklogVersion | undefined): number {
  return version && isUnderReview(version) ? version.blockers.length : 0;
}

function approvedChip(
  version: BacklogVersion,
  scope: ScopeStatus | undefined,
  versionNumber: number | null,
): StatusChip {
  const baseline = scope?.baseline_version ?? null;
  if (baseline === null || scope?.baseline_version_id === version.id) {
    return {
      text: baseline === null ? 'Baseline approved' : `Baseline v${String(baseline)} approved`,
      tone: 'accent',
    };
  }
  const name = versionNumber === null ? 'Earlier version' : `v${String(versionNumber)}`;
  return { text: `${name} · superseded by v${String(baseline)}`, tone: 'neutral' };
}

/**
 * The chip names the version in view. An approved one that is not the current baseline says
 * which baseline replaced it; `versionNumber` is its own number, from the history.
 */
export function statusChip(
  run: Run | undefined,
  version: BacklogVersion | undefined,
  sourceCount: number | undefined,
  scope?: ScopeStatus,
  versionNumber: number | null = null,
): StatusChip | null {
  if (version) {
    const revision = `r${String(version.revision)}`;
    switch (version.state) {
      case 'draft':
        return { text: `Draft ${revision} · not approved`, tone: 'warn' };
      case 'in_review':
        return { text: `Draft ${revision} · in review`, tone: 'warn' };
      case 'approved':
        return approvedChip(version, scope, versionNumber);
      case 'rejected':
        return { text: `Draft ${revision} · rejected`, tone: 'neutral' };
    }
  }
  if (run) {
    switch (run.status) {
      case 'created':
      case 'running':
        return { text: 'Agent is working', tone: 'neutral' };
      case 'waiting_for_input':
        return { text: 'Waiting for you', tone: 'warn' };
      case 'failed':
        return { text: 'Run failed', tone: 'bad' };
      case 'cancelled':
        return { text: 'Run stopped', tone: 'neutral' };
      case 'ready_for_review':
        // The saved draft says more; it is still loading.
        return null;
    }
  }
  return sourceCount === 0 ? { text: 'Setting up', tone: 'neutral' } : null;
}

interface NextStepInput {
  roleLabel: string | null;
  run: Run | undefined;
  version: BacklogVersion | undefined;
  sourceCount: number | undefined;
  chatPath: string;
  backlogPath: string;
  startRunPath: string;
  sourcesPath: string;
}

/** The one thing to do next, or null when nothing the app can do today is waiting. */
export function nextStep({
  roleLabel: role,
  run,
  version,
  sourceCount,
  chatPath,
  backlogPath,
  startRunPath,
  sourcesPath,
}: NextStepInput): NextStep | null {
  if (role === VIEWER_LABEL) {
    return { label: 'View only' };
  }
  if (version) {
    const blockers = backlogAttention(version);
    return blockers > 0
      ? { label: `Review ${plural(blockers, 'blocker')}`, to: backlogPath }
      : null;
  }
  if (run) {
    switch (run.status) {
      case 'created':
      case 'running':
        return { label: 'Agent is working', working: true };
      case 'waiting_for_input':
        return { label: `Answer ${plural(openQuestions(run), 'question')}`, to: chatPath };
      case 'failed':
      case 'cancelled':
        return { label: 'Start a new run', to: startRunPath };
      case 'ready_for_review':
        return null;
    }
  }
  if (sourceCount === undefined) {
    return null;
  }
  return sourceCount === 0
    ? { label: 'Add sources', to: sourcesPath }
    : { label: 'Start the agent run', to: startRunPath };
}
