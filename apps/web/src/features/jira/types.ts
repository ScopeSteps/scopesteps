import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];

export type JiraStatus = Schemas['ConnectionStatusResponse'];
export type JiraConnection = Schemas['ConnectionResponse'];
export type JiraPublish = Schemas['PublishResponse'];
export type JiraPreview = Schemas['PreviewResponse'];
export type KindCounts = Schemas['KindCounts'];
export type IssueKind = KindCounts['kind'];
export type Publishers = JiraConnection['publishers'];
export type JiraIssueLink = Schemas['IssueLinkResponse'];

/** Each published epic, story and task's Jira issue, by ScopeSteps item id. */
export type JiraLinks = Readonly<Record<string, JiraIssueLink>>;

/** The setup guide for teams, with why a separate Jira account is recommended. */
export const JIRA_SETUP_GUIDE =
  'https://github.com/ScopeSteps/scopesteps/blob/main/docs/product/jira-setup.md';

export function jiraKeys(projectId: string) {
  return {
    all: ['jira', projectId] as const,
    connection: ['jira', projectId, 'connection'] as const,
    issues: ['jira', projectId, 'issues'] as const,
    publishes: ['jira', projectId, 'publishes'] as const,
    preview: (versionId: string) => ['jira', projectId, 'preview', versionId] as const,
  };
}

export const KIND_WORDS: Record<IssueKind, string> = {
  epic: 'Epic',
  story: 'Story',
  task: 'Task',
};

export const KIND_HEADINGS: Record<IssueKind, string> = {
  epic: 'Epics',
  story: 'Stories',
  task: 'Tasks',
};

/** How many operations a publish or preview has, by what they do, over all kinds. */
export function totals(counts: readonly KindCounts[]) {
  return counts.reduce(
    (sum, count) => ({
      create: sum.create + count.create,
      update: sum.update + count.update,
      close: sum.close + count.close,
      unchanged: sum.unchanged + count.unchanged,
    }),
    { create: 0, update: 0, close: 0, unchanged: 0 },
  );
}
