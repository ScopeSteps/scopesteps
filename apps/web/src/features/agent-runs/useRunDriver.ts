import { useCallback, useEffect, useRef } from 'react';

import { ApiError } from '@/lib/apiError';

import { canAdvance } from './types';
import type { Run } from './types';
import { useRunCommand } from './useRunCommand';

/** Another request holds the run or moved it on; the run itself is fine. */
const BUSY_CODES = new Set(['RUN_BUSY', 'RUN_CHANGED']);
// Long enough not to hammer a run whose step is a 10 to 30 second model call.
const BUSY_RETRY_MS = 2000;

/**
 * Derived from the run's revision, so the same step requested twice (a second tab, a remount, a
 * retry after a lost response) carries the same key and the API runs it once.
 */
function advanceKey(run: Run): string {
  return `advance-${run.id}-${String(run.revision)}`;
}

/**
 * Advances a run one bounded step at a time while it can advance. It stops on its own when the
 * run waits for answers, finishes, or a step fails; a failed step is retried only by `retry`.
 */
export function useRunDriver(run: Run | undefined) {
  const runId = run?.id ?? '';
  const { mutate, reset, error, isPending } = useRunCommand(runId);
  const requested = useRef<string | null>(null);

  const isBusy = error instanceof ApiError && BUSY_CODES.has(error.code);
  const stepFailed = run?.error != null;
  const requestFailed = error !== null && !isBusy;
  const key = run && canAdvance(run) ? advanceKey(run) : null;

  useEffect(() => {
    if (key === null || stepFailed || error !== null || requested.current === key) {
      return;
    }
    requested.current = key;
    mutate({ command: { type: 'advance' }, idempotencyKey: key });
  }, [key, stepFailed, error, mutate]);

  useEffect(() => {
    if (!isBusy) {
      return;
    }
    // The failed command already refetched the run; ask again once the other request is done.
    const timer = window.setTimeout(() => {
      requested.current = null;
      reset();
    }, BUSY_RETRY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [isBusy, reset]);

  const retry = useCallback(() => {
    if (key === null) {
      return;
    }
    requested.current = key;
    mutate({ command: { type: 'advance' }, idempotencyKey: key });
  }, [key, mutate]);

  return {
    isAdvancing: isPending || isBusy || (key !== null && !stepFailed && !requestFailed),
    /** The request itself failed (network, server); the run's own failure is `run.error`. */
    requestError: requestFailed ? error : null,
    retry,
  };
}
