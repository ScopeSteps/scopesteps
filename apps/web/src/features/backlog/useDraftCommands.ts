import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { versionQueryKey } from './types';
import type { BacklogVersion, ItemPatch } from './types';

export type DraftCommand =
  | { type: 'edit'; itemId: string; patch: ItemPatch }
  | { type: 'answer'; decisionId: string; answer: string };

interface SentCommand {
  command: DraftCommand;
  expectedRevision: number;
  /** Reused when the same command is retried, so it cannot act twice. */
  idempotencyKey: string;
}

/** What a command acts on, so the row that sent it can show its progress and errors. */
export function commandTarget(command: DraftCommand): string {
  return command.type === 'edit' ? `item:${command.itemId}` : `decision:${command.decisionId}`;
}

async function send(versionId: string, { command, expectedRevision, idempotencyKey }: SentCommand) {
  const header = { 'Idempotency-Key': idempotencyKey };
  if (command.type === 'edit') {
    return api.PATCH('/api/v1/backlogs/{version_id}/items/{item_id}', {
      params: { path: { version_id: versionId, item_id: command.itemId }, header },
      body: { ...command.patch, expected_revision: expectedRevision },
    });
  }
  return api.PATCH('/api/v1/backlogs/{version_id}/decisions/{decision_id}', {
    params: { path: { version_id: versionId, decision_id: command.decisionId }, header },
    body: { answer: command.answer, expected_revision: expectedRevision },
  });
}

/**
 * Edits and answers on a draft, each at the revision the page shows. Every command answers with
 * the whole version, which replaces the cached one. A 409 is left to the page: it means the
 * draft changed elsewhere, so the reviewer reloads and looks again instead of the page retrying.
 */
export function useDraftCommands(projectId: string, version: BacklogVersion) {
  const queryClient = useQueryClient();
  const queryKey = versionQueryKey(projectId, version.id);
  const mutation = useMutation({
    mutationFn: async (sent: SentCommand) => {
      const { data, error, response } = await send(version.id, sent);
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (saved) => {
      // A read still in flight was answered before this command and must not overwrite it.
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData(queryKey, saved);
    },
  });
  const pendingKey = useRef<{ signature: string; key: string } | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);

  function sendCommand(command: DraftCommand, onSuccess?: () => void) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    const signature = JSON.stringify({ command, revision: version.revision });
    if (pendingKey.current?.signature !== signature) {
      pendingKey.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { command, expectedRevision: version.revision, idempotencyKey: pendingKey.current.key },
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

  return {
    send: sendCommand,
    isPending: mutation.isPending,
    error: mutation.error,
    /** What the last command acted on, while it is pending or after it failed. */
    target: mutation.variables ? commandTarget(mutation.variables.command) : null,
    reset: mutation.reset,
  };
}

export type DraftCommands = ReturnType<typeof useDraftCommands>;
