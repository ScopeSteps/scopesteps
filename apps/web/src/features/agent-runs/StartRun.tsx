import { useRef } from 'react';
import { Link } from 'react-router';

import { KIND_LABELS, useSources } from '@/features/sources';
import { ApiError, describeError } from '@/lib/apiError';

import { lastRunId, rememberRun } from './lastRun';
import { useStartRun } from './useStartRun';

interface StartRunProps {
  projectId: string;
  onRunSelected: (runId: string) => void;
}

export function StartRun({ projectId, onRunSelected }: StartRunProps) {
  const { data: versions, error, isPending, refetch } = useSources(projectId);
  const start = useStartRun(projectId);
  // Kept across a retry whose outcome is unknown, so it cannot create a second run.
  const idempotencyKey = useRef<string | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);
  const previousRunId = lastRunId(projectId);

  function startRun(sourceVersionIds: string[]) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    idempotencyKey.current ??= crypto.randomUUID();
    start.mutate(
      { sourceVersionIds, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (run) => {
          idempotencyKey.current = null;
          rememberRun(projectId, run.id);
          onRunSelected(run.id);
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

  return (
    <section aria-labelledby="start-run-heading">
      <h2 id="start-run-heading" className="text-lg font-semibold">
        Generate a backlog
      </h2>
      <p className="mt-1 text-sm text-gray-600">
        The agent reads the stored sources, asks you about conflicts and missing decisions, then
        drafts at most two epics and eight stories. Nothing is approved without you.
      </p>

      <div className="mt-3">
        {isPending && <p role="status">Loading sources…</p>}
        {error && (
          <div role="alert" className="text-sm text-red-700">
            <p>Could not load the stored sources. {describeError(error)}</p>
            <button type="button" onClick={() => void refetch()} className="mt-2 underline">
              Try again
            </button>
          </div>
        )}
        {versions?.length === 0 && (
          <p className="text-sm text-gray-700">
            No sources yet.{' '}
            <Link to={`/projects/${projectId}/sources`} className="text-blue-800 underline">
              Upload a project brief and a meeting transcript
            </Link>{' '}
            first.
          </p>
        )}
        {versions && versions.length > 0 && (
          <>
            <p className="text-sm font-medium">The run will read these source versions:</p>
            <ul className="mt-1 list-disc pl-5 text-sm">
              {versions.map((version) => (
                <li key={version.id}>
                  {KIND_LABELS[version.kind]}: {version.filename}, version {version.version}
                </li>
              ))}
            </ul>
            <button
              type="button"
              disabled={start.isPending}
              onClick={() => {
                startRun(versions.map((version) => version.id));
              }}
              className="mt-4 rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:opacity-60"
            >
              {start.isPending ? 'Starting…' : 'Generate backlog'}
            </button>
          </>
        )}
      </div>

      {start.error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          The run could not be started. {describeError(start.error)}
        </p>
      )}
      {previousRunId && (
        <p className="mt-4 text-sm">
          <button
            type="button"
            onClick={() => {
              onRunSelected(previousRunId);
            }}
            className="text-blue-800 underline"
          >
            Open the last run started in this browser
          </button>
        </p>
      )}
    </section>
  );
}
