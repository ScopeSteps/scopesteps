import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { conversationQueryKey, runQueryKey } from './types';
import type { Suggestion } from './types';

export interface SuggestionTarget {
  messageId: string;
  suggestion: Suggestion;
  /** The baseline a change request is made on, as this page shows it. */
  baseline: { versionId: string; contentHash: string } | null;
  /** The project's current sources, which a new draft run pins. */
  sourceVersionIds: readonly string[];
}

type Pending = 'take' | 'dismiss' | null;

/**
 * Takes or dismisses a reply's suggestion (ADR 0013). Taking it calls the endpoint a person
 * already uses for that step, which repeats every check, and only then records `accepted`. If
 * recording fails after the step worked, the next press records it again without repeating the
 * step. Each request has its own Idempotency-Key, kept for retries of the same request.
 */
export function useTakeSuggestion(projectId: string, onRunStarted: (runId: string) => void) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<Error | null>(null);
  const [stepTaken, setStepTaken] = useState(false);
  // Set synchronously, so a double press cannot send twice before the disabled state renders.
  const inFlight = useRef(false);
  const stepDone = useRef(false);
  const keys = useRef<Record<string, string>>({});

  function key(name: string): string {
    keys.current[name] ??= crypto.randomUUID();
    return keys.current[name];
  }

  async function record(target: SuggestionTarget, status: 'accepted' | 'dismissed') {
    const { error: failure, response } = await api.PUT(
      '/api/v1/projects/{project_id}/messages/{message_id}/suggestion',
      {
        params: {
          path: { project_id: projectId, message_id: target.messageId },
          header: { 'Idempotency-Key': key(status) },
        },
        body: { status, expected_revision: target.suggestion.revision },
      },
    );
    if (failure) {
      throw toApiError(failure, response);
    }
  }

  async function takeStep({ suggestion, baseline, sourceVersionIds }: SuggestionTarget) {
    switch (suggestion.kind) {
      case 'change_request': {
        if (!baseline || !suggestion.request_text) {
          throw new Error('There is no approved baseline to change yet.');
        }
        const {
          data,
          error: failure,
          response,
        } = await api.POST('/api/v1/projects/{project_id}/messages', {
          params: {
            path: { project_id: projectId },
            header: { 'Idempotency-Key': key('step') },
          },
          body: {
            kind: 'change_request',
            text: suggestion.request_text,
            base_version_id: baseline.versionId,
            base_content_hash: baseline.contentHash,
          },
        });
        if (failure) {
          throw toApiError(failure, response);
        }
        queryClient.setQueryData(runQueryKey(data.run.id), data.run);
        return;
      }
      case 'answer_decision': {
        const { version_id: versionId, decision_id: decisionId, answer } = suggestion;
        if (!versionId || !decisionId || !answer) {
          throw new Error('This suggestion no longer names a decision to answer.');
        }
        const read = await api.GET('/api/v1/projects/{project_id}/backlogs/{version_id}', {
          params: { path: { project_id: projectId, version_id: versionId } },
        });
        if (read.error) {
          throw toApiError(read.error, read.response);
        }
        const params = {
          path: { version_id: versionId, decision_id: decisionId },
          header: { 'Idempotency-Key': key('step') },
        };
        const body = { answer, expected_revision: read.data.revision };
        // A draft's decision is answered by its editors; a candidate's, by an approver.
        const answered =
          read.data.state === 'in_review'
            ? await api.POST('/api/v1/backlogs/{version_id}/candidate-decisions/{decision_id}', {
                params,
                body,
              })
            : await api.PATCH('/api/v1/backlogs/{version_id}/decisions/{decision_id}', {
                params,
                body,
              });
        if (answered.error) {
          throw toApiError(answered.error, answered.response);
        }
        await queryClient.invalidateQueries({ queryKey: ['backlog', projectId] });
        return;
      }
      case 'start_draft': {
        const {
          data,
          error: failure,
          response,
        } = await api.POST('/api/v1/projects/{project_id}/runs', {
          params: {
            path: { project_id: projectId },
            header: { 'Idempotency-Key': key('step') },
          },
          body: { mode: 'initial', source_version_ids: [...sourceVersionIds] },
        });
        if (failure) {
          throw toApiError(failure, response);
        }
        queryClient.setQueryData(runQueryKey(data.id), data);
        onRunStarted(data.id);
        return;
      }
    }
  }

  async function run(kind: 'take' | 'dismiss', target: SuggestionTarget) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(kind);
    setError(null);
    try {
      if (kind === 'take') {
        if (!stepDone.current) {
          await takeStep(target);
          stepDone.current = true;
          setStepTaken(true);
        }
        await record(target, 'accepted');
      } else {
        await record(target, 'dismissed');
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure : new Error(String(failure)));
    } finally {
      inFlight.current = false;
      setPending(null);
      await queryClient.invalidateQueries({ queryKey: conversationQueryKey(projectId) });
    }
  }

  return {
    take: (target: SuggestionTarget) => run('take', target),
    dismiss: (target: SuggestionTarget) => run('dismiss', target),
    pending,
    error,
    /** True once the step itself succeeded, even if recording it did not yet. */
    stepDone: stepTaken,
  };
}
