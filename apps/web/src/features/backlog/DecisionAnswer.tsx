import { useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { describeError } from '@/lib/apiError';

import type { Decision } from './types';

// The domain's limit on an answer (the request schema allows more).
const MAX_ANSWER = 2000;

interface DecisionAnswerProps {
  decision: Decision;
  saving: boolean;
  /** Another command is in flight, or the page is out of date. */
  disabled: boolean;
  /** A failed save, other than a stale revision, which the page reports. */
  error: Error | null;
  onAnswer: (answer: string, onSaved: () => void) => void;
}

/** Settles an open or skipped decision on a draft or a change candidate with the reviewer's answer. */
export function DecisionAnswer({
  decision,
  saving,
  disabled,
  error,
  onAnswer,
}: DecisionAnswerProps) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState('');
  const [showProblem, setShowProblem] = useState(false);
  // Set on cancel, so focus goes back to the Answer button once it is shown again.
  const returnFocus = useRef(false);
  const problem = answer.trim() ? null : 'Enter an answer.';

  function close() {
    setOpen(false);
    setShowProblem(false);
    returnFocus.current = true;
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (problem) {
      setShowProblem(true);
      return;
    }
    onAnswer(answer.trim(), () => {
      setAnswer('');
      setOpen(false);
    });
  }

  if (!open) {
    return (
      <span
        className="self-start"
        ref={(node) => {
          if (node && returnFocus.current) {
            returnFocus.current = false;
            node.querySelector('button')?.focus();
          }
        }}
      >
        <Button
          size="sm"
          aria-label={`Answer: ${decision.subject}`}
          disabled={disabled}
          onClick={() => {
            setOpen(true);
          }}
        >
          Answer
        </Button>
      </span>
    );
  }
  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={`Answer: ${decision.subject}`}
      className="flex flex-col gap-2 text-fg"
    >
      <TextField
        label="Your answer"
        value={answer}
        onChange={setAnswer}
        rows={2}
        maxLength={MAX_ANSWER}
        disabled={saving}
        help="Settles this decision. An answer can’t be changed later."
        error={showProblem ? problem : null}
        focusOnMount
      />
      {error && (
        <Banner tone="bad" role="alert">
          The answer was not saved. {describeError(error)}
        </Banner>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={disabled}>
          {saving ? 'Saving…' : 'Save answer'}
        </Button>
        <Button size="sm" disabled={saving} onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
