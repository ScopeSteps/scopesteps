import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { useReviewerName } from '@/features/identity';
import { SourcePassage } from '@/features/sources';
import { ApiError, describeError } from '@/lib/apiError';

import { MAX_ANSWER_CHARS } from './types';
import type { Question } from './types';
import { useRunCommand } from './useRunCommand';
import type { RunCommand } from './useRunCommand';

interface QuestionCardProps {
  projectId: string;
  runId: string;
  question: Question;
}

const STATUS_LABELS: Record<Question['status'], string> = {
  open: 'Needs your answer',
  answered: 'Answered',
  skipped: 'Skipped: still an open decision',
};

export function QuestionCard({ projectId, runId, question }: QuestionCardProps) {
  const send = useRunCommand(runId);
  const reviewerName = useReviewerName();
  const [answer, setAnswer] = useState('');
  // One key per attempt whose outcome is unknown, so a retry cannot submit twice.
  const idempotencyKey = useRef<string | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);
  const headingId = useId();
  const answerId = useId();
  const hintId = useId();

  function submit(command: RunCommand) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    idempotencyKey.current ??= crypto.randomUUID();
    send.mutate(
      { command, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: () => {
          idempotencyKey.current = null;
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            idempotencyKey.current = null;
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  }

  function submitAnswer(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = answer.trim();
    if (trimmed) {
      submit({ type: 'answer', questionId: question.id, answer: trimmed });
    }
  }

  return (
    <li className="rounded border border-line p-4">
      <article aria-labelledby={headingId}>
        <h3 id={headingId} className="font-semibold">
          {question.subject}
        </h3>
        <p className="mt-1 text-xs font-medium text-muted">{STATUS_LABELS[question.status]}</p>
        <p className="mt-2">{question.text}</p>
        <p className="mt-1 text-sm text-muted">
          <span className="font-medium">Why it matters:</span> {question.why_it_matters}
        </p>

        {question.evidence.length > 0 && (
          <details className="mt-3" open={question.status === 'open'}>
            <summary className="cursor-pointer text-sm font-medium">
              What the sources say ({question.evidence.length})
            </summary>
            <ul className="mt-2 space-y-2">
              {question.evidence.map((reference) => (
                <li key={reference.block_id}>
                  <SourcePassage
                    projectId={projectId}
                    sourceVersionId={reference.source_version_id}
                    blockId={reference.block_id}
                    quote={reference.quote}
                  />
                </li>
              ))}
            </ul>
          </details>
        )}

        {question.status === 'open' && (
          <form onSubmit={submitAnswer} className="mt-4">
            <label htmlFor={answerId} className="block text-sm font-medium">
              Your answer
            </label>
            <textarea
              id={answerId}
              value={answer}
              maxLength={MAX_ANSWER_CHARS}
              rows={3}
              aria-describedby={hintId}
              disabled={send.isPending}
              onChange={(event) => {
                setAnswer(event.currentTarget.value);
              }}
              className="mt-1 block w-full rounded border border-line-strong p-2 text-sm"
            />
            <p id={hintId} className="mt-1 text-xs text-muted">
              {answer.length} of {MAX_ANSWER_CHARS} characters. Your answer is saved under your name
              and cited as evidence. Skipping leaves the decision open and blocks the stories it
              affects.
            </p>
            <div className="mt-3 flex gap-3">
              <button
                type="submit"
                disabled={send.isPending || answer.trim() === ''}
                className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-fg hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
              >
                Submit answer
              </button>
              <button
                type="button"
                disabled={send.isPending}
                onClick={() => {
                  submit({ type: 'skip', questionId: question.id });
                }}
                className="rounded border border-line-strong px-4 py-2 text-sm font-medium hover:bg-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
              >
                Skip question
              </button>
            </div>
            {send.isPending && (
              <p role="status" className="mt-2 text-sm">
                Saving…
              </p>
            )}
            {send.error && (
              <p role="alert" className="mt-2 text-sm text-bad-ink">
                Your reply was not saved. {describeError(send.error)}
              </p>
            )}
          </form>
        )}

        {question.status === 'answered' && (
          <p className="mt-3 rounded bg-surface-2 p-3 text-sm">
            <span className="font-medium">Answer by {reviewerName(question.answered_by)}:</span>{' '}
            {/* Reviewer text is data: rendered as a text node. */}
            <span className="whitespace-pre-wrap">{question.answer}</span>
          </p>
        )}
        {question.status === 'skipped' && (
          <p className="mt-3 rounded bg-surface-2 p-3 text-sm">
            Skipped by {reviewerName(question.answered_by)}. No answer was assumed.
          </p>
        )}
      </article>
    </li>
  );
}
