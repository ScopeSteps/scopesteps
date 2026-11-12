import { useRef } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { ApiError, describeError } from '@/lib/apiError';

import { KIND_HEADINGS, totals } from './types';
import type { JiraPublish } from './types';
import { usePublishCommands } from './useJiraCommands';
import { useJiraPreview } from './useJiraPreview';

interface PublishPreviewModalProps {
  projectId: string;
  versionId: string;
  /** "v2", as the version is named on the page. */
  versionName: string;
  onPublished: (publish: JiraPublish) => void;
  onClose: () => void;
}

const ACTIONS = [
  { key: 'create', label: 'Create' },
  { key: 'update', label: 'Update' },
  { key: 'close', label: 'Close' },
  { key: 'unchanged', label: 'Leave as they are' },
] as const;

/**
 * What publishing would do, from the server's plan, before anything is sent. Confirming
 * starts the publish once: a second click or a retry after a lost answer reuses its key.
 */
export function PublishPreviewModal({
  projectId,
  versionId,
  versionName,
  onPublished,
  onClose,
}: PublishPreviewModalProps) {
  const preview = useJiraPreview(projectId, versionId);
  const { start } = usePublishCommands(projectId);
  const idempotencyKey = useRef<string | null>(null);
  const plan = preview.data;
  const sum = plan ? totals(plan.counts) : null;
  const nothingToDo = sum !== null && sum.create + sum.update + sum.close === 0;

  function publish() {
    if (start.isPending) {
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    start.mutate(
      { versionId, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: onPublished,
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            idempotencyKey.current = null;
          }
        },
      },
    );
  }

  let body;
  if (preview.isPending) {
    body = (
      <p role="status" className="text-subtle">
        Working out what would change in Jira…
      </p>
    );
  } else if (!plan) {
    body = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void preview.refetch()}>
            Try again
          </Button>
        }
      >
        Could not work out what would change. {preview.error && describeError(preview.error)}
      </Banner>
    );
  } else {
    const counts = plan.counts;
    body = (
      <>
        <table className="w-full border-collapse text-[13px]">
          <caption className="sr-only">What publishing does in Jira, by type</caption>
          <thead>
            <tr className="text-left text-xs text-subtle">
              <th scope="col" className="py-1 pr-3 font-medium">
                In Jira project {plan.jira_project_key}
              </th>
              {counts.map((count) => (
                <th key={count.kind} scope="col" className="py-1 pr-3 text-right font-medium">
                  {KIND_HEADINGS[count.kind]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ACTIONS.map((action) => (
              <tr key={action.key} className="border-t border-line">
                <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                  {action.label}
                </th>
                {counts.map((count) => (
                  <td key={count.kind} className="py-1.5 pr-3 text-right font-mono tabular-nums">
                    {count[action.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-subtle">
          {nothingToDo
            ? 'Jira already matches this version, so nothing would be sent.'
            : 'Closed issues stay in Jira, marked done. Tasks become Sub-tasks under their story. Nothing is sent until you confirm.'}
        </p>
      </>
    );
  }

  return (
    <Modal
      title={`Publish ${versionName} to Jira`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!plan || nothingToDo || start.isPending}
            onClick={publish}
          >
            {start.isPending ? 'Starting…' : 'Publish to Jira'}
          </Button>
        </>
      }
    >
      {body}
      {start.error && (
        <Banner tone="bad" role="alert">
          Nothing was published. {describeError(start.error)}
          {start.error instanceof ApiError && start.error.retryable && ' Try again in a moment.'}
        </Banner>
      )}
    </Modal>
  );
}
