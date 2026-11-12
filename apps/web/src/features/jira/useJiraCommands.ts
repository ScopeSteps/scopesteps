import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { jiraKeys } from './types';
import type { JiraPublish, Publishers } from './types';

export interface ConnectDetails {
  siteUrl: string;
  email: string;
  apiToken: string;
  projectKey: string;
  /** yyyy-mm-dd, or null when the person did not give it. */
  tokenExpiresOn: string | null;
}

export interface SettingsChange {
  autoPublish?: boolean;
  publishers?: Publishers;
  expectedRevision: number;
}

/** Connecting, testing, changing and removing the project's Jira connection. Approver only. */
export function useJiraConnectionCommands(projectId: string) {
  const queryClient = useQueryClient();
  const keys = jiraKeys(projectId);
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.connection }),
      queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
    ]);

  const connect = useMutation({
    mutationFn: async (details: ConnectDetails) => {
      const { data, error, response } = await api.PUT(
        '/api/v1/projects/{project_id}/jira/connection',
        {
          params: { path: { project_id: projectId } },
          body: {
            site_url: details.siteUrl,
            email: details.email,
            api_token: details.apiToken,
            project_key: details.projectKey,
            token_expires_on: details.tokenExpiresOn,
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // Moving to another Jira project forgets the earlier issue links (ADR 0029).
    onSuccess: () =>
      Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: keys.issues })]),
  });

  const test = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/jira/connection/test',
        { params: { path: { project_id: projectId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A refused token is saved as rejected even though the test fails, so refresh either way.
    onSettled: refresh,
  });

  const change = useMutation({
    mutationFn: async ({ autoPublish, publishers, expectedRevision }: SettingsChange) => {
      const { data, error, response } = await api.PATCH(
        '/api/v1/projects/{project_id}/jira/connection',
        {
          params: { path: { project_id: projectId } },
          body: {
            auto_publish: autoPublish ?? null,
            publishers: publishers ?? null,
            expected_revision: expectedRevision,
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSettled: refresh,
  });

  const disconnect = useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE(
        '/api/v1/projects/{project_id}/jira/connection',
        { params: { path: { project_id: projectId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  });

  return { connect, test, change, disconnect };
}

/** Starts a publish (once per key) and retries a failed one's failed items. */
export function usePublishCommands(projectId: string) {
  const queryClient = useQueryClient();
  const keys = jiraKeys(projectId);
  const remember = (publish: JiraPublish) => {
    queryClient.setQueryData<JiraPublish[]>(keys.publishes, (current = []) => [
      publish,
      ...current.filter((other) => other.id !== publish.id),
    ]);
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.publishes }),
      queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
    ]);
  };

  const start = useMutation({
    mutationFn: async ({
      versionId,
      idempotencyKey,
    }: {
      versionId: string;
      idempotencyKey: string;
    }) => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/jira/publishes',
        {
          params: {
            path: { project_id: projectId },
            header: { 'Idempotency-Key': idempotencyKey },
          },
          body: { version_id: versionId },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      if (!data) {
        throw new Error('The server answered without the publish.');
      }
      return data;
    },
    onSuccess: remember,
  });

  const retry = useMutation({
    mutationFn: async (publishId: string) => {
      const { data, error, response } = await api.POST(
        '/api/v1/jira/publishes/{publish_id}/retry',
        {
          params: { path: { publish_id: publishId } },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      if (!data) {
        throw new Error('The server answered without the publish.');
      }
      return data;
    },
    onSuccess: remember,
    // A refused retry can come from a token Jira stopped accepting.
    onError: () => queryClient.invalidateQueries({ queryKey: keys.connection }),
  });

  return { start, retry };
}
