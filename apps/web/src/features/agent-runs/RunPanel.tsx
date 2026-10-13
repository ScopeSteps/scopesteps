import { describeError } from '@/lib/apiError';

import { ProblemList } from './ProblemList';
import { QuestionCard } from './QuestionCard';
import type { Run } from './types';
import { useRun } from './useRun';
import { useRunCommand } from './useRunCommand';
import { useRunDriver } from './useRunDriver';

function statusLabel(run: Run, stalled: boolean): string {
  switch (run.status) {
    case 'created':
    case 'running':
      if (stalled) {
        return 'Paused: the last step did not finish';
      }
      return run.stage === 'draft' ? 'Running: writing the draft' : 'Running: reading the sources';
    case 'waiting_for_input':
      return 'Waiting for your answers';
    case 'ready_for_review':
      return 'Ready for review';
    case 'failed':
      return 'Failed';
    case 'cancelled':
      return 'Cancelled';
  }
}

interface RunPanelProps {
  projectId: string;
  runId: string;
  onRunSelected: (runId: string | null) => void;
}

export function RunPanel({ projectId, runId, onRunSelected }: RunPanelProps) {
  const { data: run, error, isPending, refetch } = useRun(runId);
  const driver = useRunDriver(run);
  const cancel = useRunCommand(runId);

  if (isPending) {
    return <p role="status">Loading the run…</p>;
  }
  // A failed background refresh keeps showing the run that is already loaded.
  if (!run) {
    return (
      <div role="alert" className="text-sm text-red-700">
        <p>Could not load the run. {describeError(error)}</p>
        <div className="mt-2 flex gap-4">
          <button type="button" onClick={() => void refetch()} className="underline">
            Try again
          </button>
          <button
            type="button"
            onClick={() => {
              onRunSelected(null);
            }}
            className="underline"
          >
            Start a new run
          </button>
        </div>
      </div>
    );
  }

  const isActive =
    run.status === 'created' || run.status === 'running' || run.status === 'waiting_for_input';
  const stalled = run.error !== null || driver.requestError !== null;
  const openQuestions = run.questions.filter((question) => question.status === 'open').length;

  return (
    <section aria-labelledby="run-heading">
      <h2 id="run-heading" className="text-lg font-semibold">
        Agent run
      </h2>
      <p role="status" className="mt-2 font-medium">
        {statusLabel(run, stalled)}
      </p>
      <p className="mt-1 text-xs text-gray-600">
        Model calls {run.usage.model_turns} of {run.limits.max_turns} · Clarification rounds{' '}
        {run.usage.clarification_rounds} of {run.limits.max_clarification_rounds} · Estimated cost $
        {run.usage.cost_usd_estimate} · {run.provider} {run.model_id} ·{' '}
        <span className="font-mono break-all">Run {run.id}</span>
      </p>

      {driver.isAdvancing && (
        <p className="mt-3 text-sm text-gray-700">
          One step can take up to half a minute. You can leave this page; the run is saved and
          resumes when you come back.
        </p>
      )}

      {run.status === 'running' && run.error && (
        <div role="alert" className="mt-3 text-sm text-red-700">
          <p>The last step failed and nothing was lost. {run.error.message}</p>
          <button type="button" onClick={driver.retry} className="mt-2 underline">
            Try the step again
          </button>
        </div>
      )}
      {driver.requestError && (
        <div role="alert" className="mt-3 text-sm text-red-700">
          <p>The run could not be advanced. {describeError(driver.requestError)}</p>
          <button type="button" onClick={driver.retry} className="mt-2 underline">
            Try the step again
          </button>
        </div>
      )}

      {run.status === 'waiting_for_input' && (
        <p className="mt-3 text-sm">
          {openQuestions === 1
            ? 'The agent needs one answer before it can draft the backlog.'
            : `The agent needs ${String(openQuestions)} answers before it can draft the backlog.`}
        </p>
      )}

      {run.status === 'failed' && (
        <div role="alert" className="mt-3 text-sm text-red-700">
          <p>
            The run stopped and no backlog was approved or changed.{' '}
            {run.error?.message ?? 'No reason was recorded.'}
          </p>
          <ProblemList problems={run.problems} />
          <button
            type="button"
            onClick={() => {
              onRunSelected(null);
            }}
            className="mt-2 underline"
          >
            Start a new run
          </button>
        </div>
      )}
      {run.status === 'cancelled' && (
        <p className="mt-3 text-sm">
          This run was cancelled.{' '}
          <button
            type="button"
            onClick={() => {
              onRunSelected(null);
            }}
            className="text-blue-800 underline"
          >
            Start a new run
          </button>
        </p>
      )}
      {run.status === 'ready_for_review' && run.problems.length > 0 && (
        <div className="mt-3 rounded border border-amber-600 bg-amber-50 p-3 text-sm">
          <p className="font-medium">
            Checks found problems the agent could not fix. Review the affected items with care:
          </p>
          <ProblemList problems={run.problems} />
        </div>
      )}

      {run.questions.length > 0 && (
        <section aria-labelledby="questions-heading" className="mt-6">
          <h3 id="questions-heading" className="font-semibold">
            Clarification questions
          </h3>
          <ul className="mt-2 space-y-3">
            {run.questions.map((question) => (
              <QuestionCard
                key={question.id}
                projectId={projectId}
                runId={run.id}
                question={question}
              />
            ))}
          </ul>
        </section>
      )}

      {isActive && (
        <div className="mt-4">
          <button
            type="button"
            disabled={cancel.isPending}
            onClick={() => {
              cancel.mutate({ command: { type: 'cancel' }, idempotencyKey: `cancel-${run.id}` });
            }}
            className="text-sm text-gray-700 underline disabled:opacity-60"
          >
            Cancel run
          </button>
          {cancel.error && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              The run was not cancelled. {describeError(cancel.error)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
