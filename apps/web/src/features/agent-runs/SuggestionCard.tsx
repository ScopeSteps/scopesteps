import { useId } from 'react';

import { Button } from '@/components/Button';
import { Tag } from '@/components/Tag';
import { describeError } from '@/lib/apiError';

import type { ThreadContext } from './threadContext';
import type { Suggestion } from './types';
import { useTakeSuggestion } from './useTakeSuggestion';

const TITLES: Record<Suggestion['kind'], string> = {
  change_request: 'Suggested: submit a change request',
  answer_decision: 'Suggested: answer an open decision',
  start_draft: 'Suggested: start a new draft run',
};

const ACTIONS: Record<Suggestion['kind'], string> = {
  change_request: 'Submit change request',
  answer_decision: 'Answer decision',
  start_draft: 'Start run',
};

const DONE: Record<Suggestion['kind'], string> = {
  change_request: 'Submitted as a change request.',
  answer_decision: 'The decision was answered.',
  start_draft: 'A new draft run was started.',
};

interface SuggestionCardProps {
  messageId: string;
  suggestion: Suggestion;
  context: ThreadContext;
}

/**
 * A next step a reply suggests, with exactly the values that would be sent (ADR 0013). Nothing
 * is sent until a person presses the action; viewers see it without buttons.
 */
export function SuggestionCard({ messageId, suggestion, context }: SuggestionCardProps) {
  const headingId = useId();
  const take = useTakeSuggestion(context.projectId, context.onRunStarted);
  const target = {
    messageId,
    suggestion,
    baseline: context.baseline,
    sourceVersionIds: context.sourceVersionIds,
  };
  const mayAct = context.canEdit || context.canApprove;
  const busy = take.pending !== null;

  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-2 rounded-xl border border-accent-line bg-surface px-3.5 py-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="font-semibold">
          {TITLES[suggestion.kind]}
        </h3>
        {suggestion.status === 'accepted' && <Tag tone="ok">Done</Tag>}
        {suggestion.status === 'dismissed' && <Tag>Dismissed</Tag>}
      </div>
      <SuggestionValues suggestion={suggestion} />
      {suggestion.status === 'accepted' && (
        <p className="text-[13px] text-muted">{DONE[suggestion.kind]}</p>
      )}
      {suggestion.status === 'offered' && !mayAct && (
        <p className="text-[13px] text-subtle">An editor or approver can take this step.</p>
      )}
      {suggestion.status === 'offered' && mayAct && (
        <>
          {!take.stepDone && (
            <p className="text-xs text-subtle">Nothing happens until you press the button.</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={busy}
              onClick={() => void take.take(target)}
            >
              {take.pending === 'take'
                ? 'Working…'
                : take.stepDone
                  ? 'Mark as done'
                  : ACTIONS[suggestion.kind]}
            </Button>
            {!take.stepDone && (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => void take.dismiss(target)}
              >
                {take.pending === 'dismiss' ? 'Dismissing…' : 'Dismiss'}
              </Button>
            )}
          </div>
        </>
      )}
      {take.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {take.stepDone
            ? 'The step was taken, but marking this suggestion as done failed. '
            : 'Nothing was changed. '}
          {describeError(take.error)}
        </p>
      )}
    </section>
  );
}

function SuggestionValues({ suggestion }: { suggestion: Suggestion }) {
  switch (suggestion.kind) {
    case 'change_request':
      return (
        <blockquote className="border-l-2 border-line pl-3 whitespace-pre-wrap [overflow-wrap:anywhere]">
          {suggestion.request_text}
        </blockquote>
      );
    case 'answer_decision':
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
          <dt className="text-subtle">Decision</dt>
          <dd className="[overflow-wrap:anywhere]">{suggestion.decision_subject}</dd>
          <dt className="text-subtle">Answer</dt>
          <dd className="[overflow-wrap:anywhere]">{suggestion.answer}</dd>
        </dl>
      );
    case 'start_draft':
      return (
        <p className="text-[13px]">
          Start a new draft run from the project&apos;s current sources.
        </p>
      );
  }
}
