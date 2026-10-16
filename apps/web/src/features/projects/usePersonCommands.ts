import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { peopleQueryKey } from './people';
import type { ConfirmableRights, PeopleResponse, Person } from './people';

export type PersonCommand =
  { type: 'correct'; name: string; role: string } | { type: 'confirm'; rights: ConfirmableRights };

interface SentCommand {
  command: PersonCommand;
  expectedRevision: number;
  /** Reused when the same command is retried, so it cannot act twice. */
  idempotencyKey: string;
}

async function send(projectId: string, personId: string, sent: SentCommand) {
  const params = {
    path: { project_id: projectId, person_id: personId },
    header: { 'Idempotency-Key': sent.idempotencyKey },
  };
  const { command, expectedRevision } = sent;
  if (command.type === 'correct') {
    return api.PUT('/api/v1/projects/{project_id}/people/{person_id}/correction', {
      params,
      body: { name: command.name, role: command.role, expected_revision: expectedRevision },
    });
  }
  return api.PUT('/api/v1/projects/{project_id}/people/{person_id}/rights', {
    params,
    body: { rights: command.rights, expected_revision: expectedRevision },
  });
}

/**
 * Corrects one person or confirms their rights, at the revision the page shows. The saved person
 * replaces the cached one. A 409 is left to the page: the person changed elsewhere, so the
 * reviewer reloads and looks again instead of the page retrying.
 */
export function usePersonCommands(projectId: string, person: Person) {
  const queryClient = useQueryClient();
  const queryKey = peopleQueryKey(projectId);
  const mutation = useMutation({
    mutationFn: async (sent: SentCommand) => {
      const { data, error, response } = await send(projectId, person.id, sent);
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (saved) => {
      // A read still in flight was answered before this command and must not overwrite it.
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData<PeopleResponse>(
        queryKey,
        (data) =>
          data && {
            ...data,
            people: data.people.map((current) => (current.id === saved.id ? saved : current)),
          },
      );
      await queryClient.invalidateQueries({ queryKey: ['activity', projectId] });
    },
  });
  const pendingKey = useRef<{ signature: string; key: string } | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);

  function sendCommand(command: PersonCommand, onSuccess?: () => void) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    const signature = JSON.stringify({ command, revision: person.revision });
    if (pendingKey.current?.signature !== signature) {
      pendingKey.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { command, expectedRevision: person.revision, idempotencyKey: pendingKey.current.key },
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
    /** Which command is pending or failed last, so its control can show it. */
    sentType: mutation.variables?.command.type ?? null,
    reset: mutation.reset,
  };
}

export type PersonCommands = ReturnType<typeof usePersonCommands>;
