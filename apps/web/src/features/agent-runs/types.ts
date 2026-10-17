import type { components } from '@scopesteps/api-client';

export type Run = components['schemas']['RunResponse'];
export type Question = components['schemas']['ClarificationQuestion'];
export type RunStatus = Run['status'];
export type Statement = components['schemas']['Statement'];
export type Message = components['schemas']['MessageResponse'];
export type Suggestion = components['schemas']['MessageSuggestion'];
export type RunLookup = components['schemas']['RunLookup'];
export type MessageClaim = components['schemas']['MessageClaim'];
export type Conversation = components['schemas']['ConversationResponse'];
export type ActiveRun = components['schemas']['ActiveRun'];
export type MessageKind = components['schemas']['PostMessageRequest']['kind'];

/** The API's limit on one answer (POC Implementation Plan, scope contract). */
export const MAX_ANSWER_CHARS = 2000;

export function runQueryKey(runId: string) {
  return ['agent-runs', runId] as const;
}

export function conversationQueryKey(projectId: string) {
  return ['conversation', projectId] as const;
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
  | { type: 'question'; runId: string; id: string }
  | { type: 'statement'; runId: string; id: string; citation: number }
  | { type: 'reply'; messageId: string; citation: number }
  | { type: 'decision'; versionId: string; id: string };

export function evidenceParam(ref: EvidenceRef): string {
  switch (ref.type) {
    case 'question':
      return `question:${ref.runId}:${ref.id}`;
    case 'statement':
      return `statement:${ref.runId}:${ref.id}:${String(ref.citation)}`;
    case 'reply':
      return `reply:${ref.messageId}:${String(ref.citation)}`;
    case 'decision':
      return `decision:${ref.versionId}:${ref.id}`;
  }
}

function index(value: string | undefined): number | null {
  const parsed = Number(value);
  return value !== undefined && Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

export function parseEvidenceParam(value: string | null): EvidenceRef | null {
  const [type, first, second, third] = value?.split(':') ?? [];
  if (!first) {
    return null;
  }
  if (type === 'question' && second) {
    return { type, runId: first, id: second };
  }
  if (type === 'decision' && second) {
    return { type, versionId: first, id: second };
  }
  if (type === 'reply') {
    const citation = index(second);
    return citation === null ? null : { type, messageId: first, citation };
  }
  const citation = index(third);
  return type === 'statement' && second && citation !== null
    ? { type, runId: first, id: second, citation }
    : null;
}
