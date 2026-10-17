import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import { AgentMessage } from './AgentMessage';
import { useStopRun } from './useStopRun';
import { canAdvance } from './types';
import type { Run, RunLookup } from './types';

export interface RunDriverState {
  isAdvancing: boolean;
  requestError: Error | null;
  retry: () => void;
}

interface ActiveRunProgressProps {
  run: Run;
  canEdit: boolean;
  driver: RunDriverState;
}

const WORKING_DOT_DELAYS = ['', '[animation-delay:150ms]', '[animation-delay:300ms]'];

function workingText(run: Run): string {
  switch (run.mode) {
    case 'reply':
      return 'Writing a reply from your sources and answers…';
    case 'change':
      return 'Analysing the change request against the baseline…';
    case 'initial':
      return run.stage === 'draft'
        ? 'Drafting the backlog from your sources and answers…'
        : 'Reading the sources…';
  }
}

const LOOKUP_TEXT: Record<RunLookup['tool'], string> = {
  lookup_source: 'Looked in the sources',
  get_story: 'Looked up a backlog item',
  list_open_decisions: 'Checked the open decisions',
};

/** What a reply has looked up so far, from its recorded steps only: never what it looked for. */
function LookupLines({ lookups }: { lookups: readonly RunLookup[] }) {
  const done = lookups.filter((lookup) => !lookup.refused);
  if (done.length === 0) {
    return null;
  }
  return (
    <ul aria-label="What the agent looked up" className="m-0 flex list-none flex-col gap-0.5 p-0">
      {done.map((lookup, index) => (
        // Lookups are only ever appended, so their position is a stable key.
        <li key={index} className="text-xs text-subtle">
          {LOOKUP_TEXT[lookup.tool]}
        </li>
      ))}
    </ul>
  );
}

/** The agent's work in progress at the end of the thread: working, or why it paused. */
export function ActiveRunProgress({ run, canEdit, driver }: ActiveRunProgressProps) {
  const cancel = useStopRun(run.id);
  const stalled = run.error !== null || driver.requestError !== null;
  const working = canAdvance(run) && !stalled;
  return (
    <>
      {run.fallback_reason && canAdvance(run) && (
        <Banner>
          The agent is using its backup provider ({run.provider}). {run.fallback_reason}
        </Banner>
      )}
      {/* Always mounted, so screen readers announce the agent starting and stopping work. */}
      <div role="status" aria-live="polite" className="contents">
        {working && (
          <AgentMessage>
            <div className="flex items-center gap-2.5 text-sm text-muted">
              <span aria-hidden="true" className="flex gap-1">
                {WORKING_DOT_DELAYS.map((delay) => (
                  <span
                    key={delay}
                    className={`size-1.5 animate-working rounded-full bg-accent ${delay}`}
                  />
                ))}
              </span>
              {workingText(run)}
            </div>
            {run.mode === 'reply' && <LookupLines lookups={run.lookups} />}
            <p className="text-xs text-subtle">
              {canEdit
                ? 'One step can take up to half a minute. You can leave this page; the work is saved and resumes when you come back.'
                : 'An editor’s session moves the work on. This page shows their progress.'}
            </p>
          </AgentMessage>
        )}
      </div>
      {run.status === 'waiting_for_input' && canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={cancel.stop}>
            Stop the run
          </Button>
          {cancel.error && (
            <span role="alert" className="text-[13px] text-bad-ink">
              The run was not stopped. {describeError(cancel.error)}
            </span>
          )}
        </div>
      )}
      {canAdvance(run) && run.error && (
        <Banner
          tone="bad"
          role="alert"
          action={
            canEdit && (
              <Button size="sm" onClick={driver.retry}>
                Try the step again
              </Button>
            )
          }
        >
          The last step failed and nothing was lost. {run.error.message}
        </Banner>
      )}
      {driver.requestError && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={driver.retry}>
              Try the step again
            </Button>
          }
        >
          The agent could not be moved on. {describeError(driver.requestError)}
        </Banner>
      )}
    </>
  );
}
