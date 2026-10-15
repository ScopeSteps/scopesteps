import { useEffect, useId, useState } from 'react';
import type { KeyboardEvent, RefObject, SubmitEvent } from 'react';

import { Icon } from '@/components/Icon';
import { useCurrentUser } from '@/features/identity';
import { AddSourceButton } from '@/features/sources';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { canAdvance, MAX_ANSWER_CHARS, openQuestions } from './types';
import type { Question, Run } from './types';
import { useKeyedRunCommand } from './useKeyedRunCommand';
import { useStopRun } from './useStopRun';

interface ComposerProps {
  projectId: string;
  /** The run in the thread, or undefined before one is started or while it loads. */
  run: Run | undefined;
  canEdit: boolean;
  /** The open question the composer answers, chosen with its Answer button. */
  answering: Question | null;
  onStopAnswering: () => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}

const ROUND_BUTTON =
  'flex size-[34px] flex-none cursor-pointer items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-35';

function placeholder(
  canEdit: boolean,
  roleKnown: boolean,
  run: Run | undefined,
  answering: Question | null,
) {
  if (!roleKnown) {
    return 'Message ScopeSteps…';
  }
  if (!canEdit) {
    return 'View-only access. An editor can reply to the agent.';
  }
  if (!run) {
    return 'Add sources and start the run to chat with ScopeSteps';
  }
  if (answering) {
    return 'Type your answer…';
  }
  return openQuestions(run).length > 0 && run.status === 'waiting_for_input'
    ? 'Choose Answer on a question to reply'
    : 'The agent has no question for you right now';
}

/**
 * Answers the agent's questions. Until the conversation API exists it sends nothing else, and
 * its hint says so. While the agent works, its send button stops the run instead.
 */
export function Composer({
  projectId,
  run,
  canEdit,
  answering,
  onStopAnswering,
  inputRef,
}: ComposerProps) {
  const [text, setText] = useState('');
  const { data: user } = useCurrentUser();
  const answer = useKeyedRunCommand(run?.id ?? '');
  const cancel = useStopRun(run?.id ?? '');
  const hintId = useId();
  const inputId = useId();

  const canAnswer = canEdit && answering !== null && run?.status === 'waiting_for_input';
  const answeringId = answering?.id;

  // Choosing Answer on a question moves the cursor here, once the field is enabled for it.
  useEffect(() => {
    if (answeringId !== undefined) {
      inputRef.current?.focus();
    }
  }, [answeringId, inputRef]);
  const canStop = canEdit && run !== undefined && canAdvance(run);

  function submit(event?: SubmitEvent<HTMLFormElement>) {
    event?.preventDefault();
    const trimmed = text.trim();
    if (!canAnswer || trimmed === '') {
      return;
    }
    answer.send({ type: 'answer', questionId: answering.id, answer: trimmed }, () => {
      setText('');
      onStopAnswering();
    });
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="mx-auto w-full max-w-[760px] flex-none px-5 pt-1.5 pb-4 max-wide:px-3">
      <form
        onSubmit={submit}
        aria-label="Reply to the agent"
        className="flex flex-col gap-1.5 rounded-2xl border border-line-strong bg-surface py-2 pr-2.5 pl-3.5 shadow-raised focus-within:border-accent focus-within:shadow-focus"
      >
        {answering && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-accent-soft py-[3px] pr-1 pl-[9px] text-xs font-semibold text-accent-ink">
              <span className="truncate">Answering: {answering.text}</span>
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
          maxLength={MAX_ANSWER_CHARS}
          placeholder={placeholder(canEdit, user !== undefined, run, answering)}
          aria-describedby={hintId}
          disabled={!canAnswer || answer.isPending}
          onChange={(event) => {
            setText(event.currentTarget.value);
          }}
          onKeyDown={onKeyDown}
          className="max-h-[200px] min-h-[26px] w-full resize-none border-none bg-transparent px-0 py-0.5 text-[15px] leading-normal outline-none [field-sizing:content] placeholder:text-subtle disabled:cursor-not-allowed"
        />
        <div className="flex items-center gap-1.5">
          {canEdit && <AddSourceButton projectId={projectId} iconOnly label="Add a source" />}
          <span className="ml-auto font-mono text-xs text-subtle tabular-nums">
            {text.length} / {MAX_ANSWER_CHARS}
          </span>
          {canStop ? (
            <button
              type="button"
              aria-label="Stop the agent"
              title="Stop the agent"
              disabled={cancel.isPending}
              onClick={cancel.stop}
              className={cx(ROUND_BUTTON, 'bg-fg text-bg')}
            >
              <Icon name="stop" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label="Send"
              title="Send"
              disabled={!canAnswer || answer.isPending || text.trim() === ''}
              className={cx(ROUND_BUTTON, 'bg-accent text-accent-fg enabled:hover:bg-accent-hover')}
            >
              <Icon name="send" />
            </button>
          )}
        </div>
      </form>
      <p id={hintId} className="mt-2 text-center text-[11px] text-subtle">
        Enter to send · Shift + Enter for a new line · For now the agent reads only answers to its
        questions. Check citations before approving.
      </p>
      {answer.isPending && (
        <p role="status" className="mt-1 text-center text-xs text-subtle">
          Saving your answer…
        </p>
      )}
      {answer.error && (
        <p role="alert" className="mt-1 text-center text-[13px] text-bad-ink">
          Your reply was not saved. {describeError(answer.error)}
        </p>
      )}
      {cancel.error && (
        <p role="alert" className="mt-1 text-center text-[13px] text-bad-ink">
          The run was not stopped. {describeError(cancel.error)}
        </p>
      )}
    </div>
  );
}
