import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '@/lib/api';
import { ApiError, describeError, toApiError } from '@/lib/apiError';

import { conversationQueryKey, runQueryKey } from './types';
import type { MessageKind } from './types';

/** A message this browser sent that the thread does not show as stored yet. */
export interface OutgoingMessage {
  localId: string;
  /** Sent with every attempt, so a retry after an unknown outcome is stored once. */
  idempotencyKey: string;
  text: string;
  kind: MessageKind;
  /** A change request names the baseline as the requester saw it. */
  base: { versionId: string; contentHash: string } | null;
  status: 'sending' | 'failed';
  error: string | null;
}

function storageKey(projectId: string): string {
  return `scopesteps:outbox:${projectId}`;
}

function load(projectId: string): OutgoingMessage[] {
  try {
    const stored: unknown = JSON.parse(
      window.sessionStorage.getItem(storageKey(projectId)) ?? '[]',
    );
    if (!Array.isArray(stored)) {
      return [];
    }
    // A send that was in flight when the page went away has an unknown outcome: retrying it
    // with its key is safe, so it comes back as one to retry.
    return (stored as OutgoingMessage[])
      .filter((message) => typeof message.text === 'string' && typeof message.localId === 'string')
      .map((message) => ({
        ...message,
        status: 'failed',
        error: message.error ?? 'The page was reloaded before the message was confirmed.',
      }));
  } catch {
    return [];
  }
}

function save(projectId: string, messages: OutgoingMessage[]): void {
  try {
    if (messages.length === 0) {
      window.sessionStorage.removeItem(storageKey(projectId));
    } else {
      window.sessionStorage.setItem(storageKey(projectId), JSON.stringify(messages));
    }
  } catch {
    // Storage can be unavailable (private mode, quota); the message is then kept until reload.
  }
}

/**
 * Sends messages to the agent and keeps those not yet stored, with why, so a failed one stays
 * in the thread to retry or discard. Kept for this tab in session storage, never anywhere else.
 */
export function useOutbox(projectId: string) {
  const queryClient = useQueryClient();
  const [outbox, setOutbox] = useState<OutgoingMessage[]>(() => load(projectId));
  const sending = useRef(new Set<string>());

  useEffect(() => {
    save(projectId, outbox);
  }, [projectId, outbox]);

  const update = useCallback((localId: string, change: Partial<OutgoingMessage> | null) => {
    setOutbox((current) =>
      change === null
        ? current.filter((message) => message.localId !== localId)
        : current.map((message) =>
            message.localId === localId ? { ...message, ...change } : message,
          ),
    );
  }, []);

  const post = useCallback(
    async (message: OutgoingMessage) => {
      if (sending.current.has(message.localId)) {
        return;
      }
      sending.current.add(message.localId);
      update(message.localId, { status: 'sending', error: null });
      try {
        const { data, error, response } = await api.POST('/api/v1/projects/{project_id}/messages', {
          params: {
            path: { project_id: projectId },
            header: { 'Idempotency-Key': message.idempotencyKey },
          },
          body: {
            kind: message.kind,
            text: message.text,
            ...(message.base
              ? {
                  base_version_id: message.base.versionId,
                  base_content_hash: message.base.contentHash,
                }
              : {}),
          },
        });
        if (error) {
          throw toApiError(error, response);
        }
        queryClient.setQueryData(runQueryKey(data.run.id), data.run);
        await queryClient.invalidateQueries({ queryKey: conversationQueryKey(projectId) });
        update(message.localId, null);
      } catch (failure) {
        update(message.localId, { status: 'failed', error: describeFailure(failure) });
        if (failure instanceof ApiError && failure.code === 'BASELINE_CHANGED') {
          // The toggle and the baseline it names are refreshed for the next attempt.
          await queryClient.invalidateQueries({ queryKey: ['projects'] });
        }
      } finally {
        sending.current.delete(message.localId);
      }
    },
    [projectId, queryClient, update],
  );

  const send = useCallback(
    (text: string, kind: MessageKind, base: OutgoingMessage['base']) => {
      const message: OutgoingMessage = {
        localId: crypto.randomUUID(),
        idempotencyKey: crypto.randomUUID(),
        text,
        kind,
        base,
        status: 'sending',
        error: null,
      };
      setOutbox((current) => [...current, message]);
      void post(message);
    },
    [post],
  );

  return {
    outbox,
    send,
    retry: (message: OutgoingMessage) => void post(message),
    discard: (message: OutgoingMessage) => {
      update(message.localId, null);
    },
  };
}

function describeFailure(failure: unknown): string {
  if (failure instanceof ApiError) {
    switch (failure.code) {
      case 'AGENT_BUSY':
        return 'The agent is busy with other work. Try again once it has finished.';
      case 'BASELINE_REQUIRED':
        return 'A change request needs an approved baseline.';
      case 'BASELINE_CHANGED':
        return 'The baseline changed since you wrote this. Check the new baseline, then try again.';
    }
  }
  return describeError(failure instanceof Error ? failure : new Error(String(failure)));
}
