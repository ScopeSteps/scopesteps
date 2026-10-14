import type { components } from '@scopesteps/api-client';

export type Run = components['schemas']['RunResponse'];
export type Question = components['schemas']['ClarificationQuestion'];
export type RunStatus = Run['status'];
export type Statement = components['schemas']['Statement'];

/** The API's limit on one answer (POC Implementation Plan, scope contract). */
export const MAX_ANSWER_CHARS = 2000;

export function runQueryKey(runId: string) {
  return ['agent-runs', runId] as const;
}

export function canAdvance(run: Run): boolean {
  return run.status === 'created' || run.status === 'running';
}

/** The run can still change: the agent works on it or waits for answers. */
export function isActive(run: Run): boolean {
  return canAdvance(run) || run.status === 'waiting_for_input';
}

export function openQuestions(run: Run): Question[] {
  return run.questions.filter((question) => question.status === 'open');
}

/** What a chat citation chip or question opens, as it appears in the URL. */
export type EvidenceRef =
  { type: 'question'; id: string } | { type: 'statement'; id: string; citation: number };

export function evidenceParam(ref: EvidenceRef): string {
  return ref.type === 'question'
    ? `question:${ref.id}`
    : `statement:${ref.id}:${String(ref.citation)}`;
}

export function parseEvidenceParam(value: string | null): EvidenceRef | null {
  const [type, id, citation] = value?.split(':') ?? [];
  if (!id) {
    return null;
  }
  if (type === 'question') {
    return { type, id };
  }
  const index = Number(citation);
  return type === 'statement' && Number.isInteger(index) && index >= 0
    ? { type, id, citation: index }
    : null;
}
