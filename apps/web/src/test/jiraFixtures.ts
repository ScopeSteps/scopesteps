import type { components } from '@scopesteps/api-client';

import { REVIEWER_ID, VERSION_ID } from '@/test/fixtures';

type Schemas = components['schemas'];

export const PUBLISH_ID = '019a3a5e-0000-7000-8000-0000000000a1';

/** A working connection to the synthetic Jira project WEB, as an approver sees it. */
export function jiraConnection(
  overrides: Partial<Schemas['ConnectionResponse']> = {},
): Schemas['ConnectionResponse'] {
  return {
    site_url: 'https://example-team.atlassian.net',
    email: 'scopesteps-bot@example.test',
    jira_project_key: 'WEB',
    jira_project_name: 'Website',
    jira_account_name: 'ScopeSteps Bot',
    token_state: 'working',
    token_expires_on: null,
    token_days_left: null,
    token_rejected_at: null,
    auto_publish: false,
    publishers: 'approvers',
    connected_by: REVIEWER_ID,
    connected_at: '2026-11-01T09:00:00Z',
    checked_at: '2026-11-10T09:00:00Z',
    revision: 3,
    ...overrides,
  };
}

export function jiraStatus(
  connection: Schemas['ConnectionResponse'] | null,
  { canManage = true, canPublish = connection !== null, configured = true } = {},
): Schemas['ConnectionStatusResponse'] {
  return { configured, connection, can_publish: canPublish, can_manage: canManage };
}

export function kindCounts(
  create: [number, number, number],
  update: [number, number, number] = [0, 0, 0],
  close: [number, number, number] = [0, 0, 0],
): Schemas['KindCounts'][] {
  return (['epic', 'story', 'task'] as const).map((kind, index) => ({
    kind,
    create: create[index] ?? 0,
    update: update[index] ?? 0,
    close: close[index] ?? 0,
    unchanged: 0,
  }));
}

export function jiraPublish(
  overrides: Partial<Schemas['PublishResponse']> = {},
): Schemas['PublishResponse'] {
  return {
    id: PUBLISH_ID,
    version_id: VERSION_ID,
    status: 'sending',
    created_by: REVIEWER_ID,
    created_at: '2026-11-11T09:00:00Z',
    finished_at: null,
    last_error: null,
    next_attempt_at: null,
    total: 3,
    sent: 0,
    counts: kindCounts([1, 1, 1]),
    failed: [],
    revision: 1,
    ...overrides,
  };
}
