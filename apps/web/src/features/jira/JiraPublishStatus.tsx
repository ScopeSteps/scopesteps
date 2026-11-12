import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

import { KIND_WORDS, totals } from './types';
import type { JiraPublish } from './types';
import { usePublishCommands } from './useJiraCommands';
import { useJiraConnection } from './useJiraConnection';
import { useJiraPublishes } from './useJiraPublishes';

const ITEM_PROBLEMS: Record<string, string> = {
  JIRA_REJECTED: 'Jira refused its fields',
  JIRA_NO_DONE_STATUS: 'Jira has no Done status to close it with',
  PARENT_NOT_PUBLISHED: 'its epic or story did not reach Jira',
  JIRA_UNAVAILABLE: 'Jira did not answer',
};

const WHOLE_PROBLEMS: Record<string, string> = {
  JIRA_AUTH_FAILED: 'Jira refused the API token.',
  JIRA_TOKEN_REJECTED: 'Jira refused the API token.',
  JIRA_TOKEN_EXPIRED: 'The Jira API token expired.',
  JIRA_FORBIDDEN: 'The Jira account may not create issues in that project.',
  JIRA_NOT_CONNECTED: 'Jira was disconnected.',
};

const OPERATIONS = { create: 'create', update: 'update', close: 'close' } as const;

interface JiraPublishStatusProps {
  projectId: string;
  versionId: string;
  /** Each item's title by id, so a failure names what did not reach Jira. */
  itemTitles: Readonly<Record<string, string>>;
}

function summary(publish: JiraPublish): string {
  const sum = totals(publish.counts);
  const parts = [
    sum.create > 0 && `${String(sum.create)} created`,
    sum.update > 0 && `${String(sum.update)} updated`,
    sum.close > 0 && `${String(sum.close)} closed`,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(', ') : 'nothing to change';
}

/**
 * The newest Jira publish of the version in view, for someone who may publish: progress while
 * the server sends it, what it did once done, and the items that failed with a retry.
 */
export function JiraPublishStatus({ projectId, versionId, itemTitles }: JiraPublishStatusProps) {
  const { data: status } = useJiraConnection(projectId);
  const canPublish = status?.can_publish === true;
  const publishes = useJiraPublishes(projectId, canPublish);
  const { retry } = usePublishCommands(projectId);
  const publish = publishes.data?.find((each) => each.version_id === versionId);
  if (!canPublish || !publish) {
    return null;
  }

  if (publish.status === 'sending') {
    const waiting =
      publish.last_error === 'JIRA_RATE_LIMITED'
        ? 'Jira asked to slow down'
        : publish.last_error === 'JIRA_UNAVAILABLE'
          ? 'Jira could not be reached'
          : null;
    return (
      <Banner role="status">
        Publishing to Jira: {publish.sent} of {publish.total} sent.
        {waiting && publish.next_attempt_at
          ? ` ${waiting}, so it tries again at ${formatWhen(publish.next_attempt_at)}.`
          : ' It keeps going if you leave the page.'}
      </Banner>
    );
  }

  if (publish.status === 'done') {
    return (
      <p role="status" className="-mt-2 text-xs text-subtle">
        Published to Jira {publish.finished_at ? formatWhen(publish.finished_at) : ''}:{' '}
        {summary(publish)}.
      </p>
    );
  }

  const whole = publish.last_error ? WHOLE_PROBLEMS[publish.last_error] : undefined;
  const count = publish.failed.length;
  return (
    <Banner
      tone="bad"
      role="alert"
      action={
        <Button
          size="sm"
          disabled={retry.isPending}
          onClick={() => {
            retry.mutate(publish.id);
          }}
        >
          {retry.isPending ? 'Retrying…' : count > 0 ? 'Retry failed items' : 'Retry'}
        </Button>
      }
    >
      <span className="flex flex-col gap-1">
        <span>
          <strong className="font-semibold">
            {count > 0
              ? `${String(count)} ${count === 1 ? 'item' : 'items'} did not reach Jira.`
              : 'Publishing to Jira stopped.'}
          </strong>{' '}
          {whole ?? ''} {publish.sent} of {publish.total} were sent. Retry sends only what is
          missing.
        </span>
        {count > 0 && (
          <ul aria-label="Items that did not reach Jira" className="m-0 list-disc pl-5 text-xs">
            {publish.failed.map((item) => (
              <li key={`${item.item_id}-${item.operation}`}>
                {KIND_WORDS[item.kind]} “{itemTitles[item.item_id] ?? 'removed item'}
                ”: could not {OPERATIONS[item.operation]} it, because{' '}
                {ITEM_PROBLEMS[item.error_code] ?? `of ${item.error_code}`}.
              </li>
            ))}
          </ul>
        )}
        {retry.error && <span>The retry did not start. {describeError(retry.error)}</span>}
      </span>
    </Banner>
  );
}
