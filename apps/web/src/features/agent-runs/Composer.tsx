import { useEffect, useId, useState } from 'react';
import type { KeyboardEvent, RefObject, SubmitEvent } from 'react';

import { Icon } from '@/components/Icon';
import { AddSourceButton } from '@/features/sources';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { loadDraft, saveDraft } from './draft';
import { MAX_ANSWER_CHARS } from './types';
import type { MessageKind, Question, Run } from './types';
import { useKeyedRunCommand } from './useKeyedRunCommand';
import { useStopRun } from './useStopRun';

/** Whether a change request can be sent now, and why not when it cannot. */
export type ChangeRequestOption =
  | { available: true; base: { versionId: string; contentHash: string } }
  | { available: false; reason: string };

interface ComposerProps {
  projectId: string;
  /** Null until the user's role is known. */
  canEdit: boolean | null;
  /** The API's limit on one message, or null until the project is loaded. */
  maxChars: number | null;
  /** The question the composer answers, chosen on its card, with the run it belongs to. */
  answering: { run: Run; question: Question } | null;
  onStopAnswering: () => void;
  /** Agent work that is created or running: Send becomes Stop. */
  workingRunId: string | null;
  /** Whether the project has an approved baseline, which both choices below need. */
  canDiscuss: boolean;
  changeRequest: ChangeRequestOption;
  onSend: (text: string, kind: MessageKind) => void;
  /** Called whenever a message or an answer is sent, so the thread can show it. */
  onSubmitted: () => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}

const ROUND_BUTTON =
  'flex size-[34px] flex-none cursor-pointer items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-35';

/** The counter appears once this share of the limit is used. */
const SHOW_COUNT_FROM = 0.8;

/** What each way of sending does, in one plain line. */
const MODES = {
  discuss: {
    label: 'Talk it through',
    hint: 'The agent says whether the idea fits and how it could work. Nothing changes.',
    placeholder: 'Describe the change you want to talk through…',
  },
  change_request: {
    label: 'Request a change',
    hint: 'The agent analyses it against the approved baseline and proposes a change to review.',
    placeholder: 'Describe the change to the approved baseline…',
  },
} as const;

const NO_MODE_HINT = 'Ask a question, or choose how to raise a change.';

function placeholder(
  canEdit: boolean | null,
  working: boolean,
  answering: boolean,
  mode: MessageKind,
) {
  if (canEdit === null) {
    return 'Message ScopeSteps…';
  }
  if (!canEdit) {
    return 'View-only access. An editor can message the agent.';
  }
  if (answering) {
    return 'Type your answer…';
  }
  if (working) {
    return 'The agent is working. Stop it to send something else.';
  }
  return mode === 'message' ? 'Message ScopeSteps…' : MODES[mode].placeholder;
}

/**
 * Sends a message, a change to talk through, a change request or the answer to the question
 * being answered. While the agent works, its send button stops the work instead.
 */
export function Composer({
  projectId,
  canEdit,
  maxChars,
  answering,
  onStopAnswering,
  workingRunId,
  canDiscuss,
  changeRequest,
  onSend,
  onSubmitted,
  inputRef,
}: ComposerProps) {
  const [text, setText] = useState(() => loadDraft(projectId));
  const [chosen, setChosen] = useState<MessageKind>('message');
  const answer = useKeyedRunCommand(answering?.run.id ?? '');
  const cancel = useStopRun(workingRunId ?? '');
  const hintId = useId();
  const inputId = useId();
  const modeHintId = useId();

  const editor = canEdit === true;
  const working = workingRunId !== null;
  // A choice the project no longer allows falls back to a plain message.
  const mode: MessageKind =
    answering || !canDiscuss || (chosen === 'change_request' && !changeRequest.available)
      ? 'message'
      : chosen;
  const limit = answering ? MAX_ANSWER_CHARS : (maxChars ?? MAX_ANSWER_CHARS);
  const trimmed = text.trim();
  const canSend = editor && trimmed !== '' && trimmed.length <= limit && !answer.isPending;
  const answeringId = answering?.question.id;
  const changingAnswer = answering !== null && answering.question.status !== 'open';

  useEffect(() => {
    saveDraft(projectId, text);
  }, [projectId, text]);

  // Choosing Answer on a question moves the cursor here.
  useEffect(() => {
    if (answeringId !== undefined) {
      inputRef.current?.focus();
    }
  }, [answeringId, inputRef]);

  function submit(event?: SubmitEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!canSend) {
      return;
    }
    if (answering) {
      answer.send(
        {
          type: 'answer',
          questionId: answering.question.id,
          answer: trimmed,
          ...(changingAnswer ? { expectedRevision: answering.run.revision } : {}),
        },
        () => {
          setText('');
          onStopAnswering();
        },
      );
      onSubmitted();
      return;
    }
    if (working) {
      return;
    }
    onSend(trimmed, mode);
    onSubmitted();
    setText('');
    setChosen('message');
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const showStop = editor && working && !answering;
  const showCount = text.length >= limit * SHOW_COUNT_FROM;
  const over = text.length > limit;

  return (
    <div className="mx-auto w-full max-w-[760px] flex-none px-5 pt-1.5 pb-4 max-wide:px-3">
      <form
        onSubmit={submit}
        aria-label="Message the agent"
        className={cx(
          'flex flex-col gap-1.5 rounded-2xl border bg-surface py-2 pr-2.5 pl-3.5 shadow-raised focus-within:border-accent focus-within:shadow-focus',
          mode === 'message' ? 'border-line-strong' : 'border-accent-line',
        )}
      >
        {answering && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-accent-soft py-[3px] pr-1 pl-[9px] text-xs font-semibold text-accent-ink">
              <span className="truncate">
                {changingAnswer ? 'Changing the answer to' : 'Answering'}: {answering.question.text}
              </span>
              <button
                type="button"
                aria-label="Stop answering this question"
                onClick={onStopAnswering}
                className="flex size-5 cursor-pointer items-center justify-center rounded-full"
              >
                <Icon name="close" size={12} />
              </button>
            </span>
          </div>
        )}
        <label htmlFor={inputId} className="sr-only">
          Message ScopeSteps
        </label>
        <textarea
          ref={inputRef}
          id={inputId}
          rows={1}
          value={text}
          placeholder={placeholder(canEdit, working, answering !== null, mode)}
          aria-describedby={hintId}
          aria-invalid={over || undefined}
          disabled={!editor || answer.isPending || (working && !answering)}
          onChange={(event) => {
            setText(event.currentTarget.value);
          }}
          onKeyDown={onKeyDown}
          className="max-h-[200px] min-h-[26px] w-full resize-none border-none bg-transparent px-0 py-0.5 text-[15px] leading-normal outline-none [field-sizing:content] placeholder:text-subtle disabled:cursor-not-allowed"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          {editor && <AddSourceButton projectId={projectId} iconOnly label="Add a source" />}
          {editor && !answering && canDiscuss && (
            <div role="group" aria-label="How to raise a change" className="flex gap-1.5">
              {(['discuss', 'change_request'] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={mode === kind}
                  aria-describedby={modeHintId}
                  disabled={kind === 'change_request' && !changeRequest.available}
                  onClick={() => {
                    setChosen((current) => (current === kind ? 'message' : kind));
                  }}
                  className={cx(
                    'inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50',
                    mode === kind
                      ? 'border-accent bg-accent-soft text-accent-ink'
                      : 'border-line text-muted',
                  )}
                >
                  {MODES[kind].label}
                </button>
              ))}
            </div>
          )}
          {editor && !answering && canDiscuss && (
            <span id={modeHintId} className="text-xs text-subtle">
              {mode !== 'message'
                ? MODES[mode].hint
                : changeRequest.available
                  ? NO_MODE_HINT
                  : changeRequest.reason}
            </span>
          )}
          {showCount && (
            <span
              className={cx(
                'ml-auto font-mono text-xs tabular-nums',
                over ? 'text-bad-ink' : 'text-subtle',
              )}
            >
              {text.length} / {limit}
              <span className="sr-only"> characters</span>
            </span>
          )}
          {showStop ? (
            <button
              type="button"
              aria-label="Stop the agent"
              title="Stop the agent"
              disabled={cancel.isPending}
              onClick={cancel.stop}
              className={cx(ROUND_BUTTON, 'ml-auto bg-fg text-bg')}
            >
              <Icon name="stop" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label="Send"
              title="Send"
              disabled={!canSend || (working && !answering)}
              className={cx(
                ROUND_BUTTON,
                !showCount && 'ml-auto',
                'bg-accent text-accent-fg enabled:hover:bg-accent-hover',
              )}
            >
              <Icon name="send" />
            </button>
          )}
        </div>
      </form>
      <p id={hintId} className="mt-2 text-center text-[11px] text-subtle">
        {canEdit === false
          ? 'You have view-only access to this project, so you cannot message the agent.'
          : `Enter to send · Shift + Enter for a new line · Up to ${limit.toLocaleString()} characters · Check citations before approving.`}
      </p>
      {over && (
        <p role="alert" className="mt-1 text-center text-[13px] text-bad-ink">
          This is {(text.length - limit).toLocaleString()} characters over the limit.
        </p>
      )}
      {answer.isPending && (
        <p role="status" className="mt-1 text-center text-xs text-subtle">
          Saving your answer…
        </p>
      )}
      {answer.error && (
        <p role="alert" className="mt-1 text-center text-[13px] text-bad-ink">
          Your answer was not saved. {describeError(answer.error)}
        </p>
      )}
      {cancel.error && (
        <p role="alert" className="mt-1 text-center text-[13px] text-bad-ink">
          The agent was not stopped. {describeError(cancel.error)}
        </p>
      )}
    </div>
  );
}
