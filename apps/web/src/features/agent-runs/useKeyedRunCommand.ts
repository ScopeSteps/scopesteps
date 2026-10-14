import { useRef } from 'react';

import { ApiError } from '@/lib/apiError';

import { useRunCommand } from './useRunCommand';
import type { RunCommand } from './useRunCommand';

/**
 * Sends a reviewer's command to a run at most once. The same command retried after an unknown
 * outcome reuses its key; a different command, or one the API has answered, gets a new key.
 */
export function useKeyedRunCommand(runId: string) {
  const command = useRunCommand(runId);
  const pendingKey = useRef<{ command: string; key: string } | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);

  function send(next: RunCommand, onSuccess?: () => void) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    const signature = JSON.stringify(next);
    if (pendingKey.current?.command !== signature) {
      pendingKey.current = { command: signature, key: crypto.randomUUID() };
    }
    command.mutate(
      { command: next, idempotencyKey: pendingKey.current.key },
      {
        onSuccess: () => {
          pendingKey.current = null;
          onSuccess?.();
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            pendingKey.current = null;
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  }

  return { send, isPending: command.isPending, error: command.error, reset: command.reset };
}
