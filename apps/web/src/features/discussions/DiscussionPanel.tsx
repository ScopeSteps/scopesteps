import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { SegmentedControl } from '@/components/SegmentedControl';
import { useVersionHistory, versionName } from '@/features/backlog';
import { useCurrentUser } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { Composer } from './Composer';
import { ThreadCard } from './ThreadCard';
import type { DiscussionScope, ThreadFilter } from './types';
import { useDiscussionCommands, useThreads } from './useDiscussions';

const FILTERS = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
] as const satisfies readonly { value: ThreadFilter; label: string }[];

interface DiscussionPanelProps {
  projectId: string;
  scope: DiscussionScope;
}

/**
 * One item's discussions, or the whole project's with General discussion: a box to start a
 * thread, then the threads, newest activity first. Comments never change the backlog.
 */
export function DiscussionPanel({ projectId, scope }: DiscussionPanelProps) {
  const [filter, setFilter] = useState<ThreadFilter>(scope.kind === 'item' ? 'all' : 'open');
  const [focusCommentId, setFocusCommentId] = useState<string | null>(null);
  const threads = useThreads(projectId, scope, filter);
  const { run } = useDiscussionCommands(projectId);
  const { data: user } = useCurrentUser();
  const { data: versions } = useVersionHistory(projectId);
  const roles =
    user?.memberships.filter((m) => m.project_id === projectId).map((m) => m.role) ?? [];
  const resolvesAny = roles.includes('editor') || roles.includes('approver');
  const listed = threads.data?.pages.flatMap((page) => page.threads) ?? [];

  function versionLabel(versionId: string | null): string | null {
    const version = versionId === null ? undefined : versions?.find((v) => v.id === versionId);
    if (!version) {
      return null;
    }
    switch (version.state) {
      case 'approved':
        return `about ${versionName(version.number)}`;
      case 'in_review':
        return 'about a candidate in review';
      case 'draft':
      case 'rejected':
        return 'about a draft';
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Composer
        projectId={projectId}
        draftKey={scope.kind === 'item' ? `new:${scope.itemId}` : 'new:general'}
        label={scope.kind === 'item' ? 'Start a discussion' : 'Start a General discussion'}
        placeholder={
          scope.kind === 'item'
            ? 'Start a discussion about this item…'
            : 'Share an idea that is not tied to an item yet…'
        }
        submitLabel="Start discussion"
        onSubmit={async (body) => {
          const thread = await run({
            type: 'start',
            itemId: scope.kind === 'item' ? scope.itemId : null,
            body,
          });
          if (filter === 'resolved') {
            setFilter('open');
          }
          const first = thread?.comments[0];
          if (first) {
            setFocusCommentId(first.id);
          }
        }}
      />
      {scope.kind === 'project' && (
        <SegmentedControl
          label="Show discussions"
          options={FILTERS}
          value={filter}
          onChange={setFilter}
        />
      )}
      {threads.isPending ? (
        <p role="status" className="text-subtle">
          Loading discussions…
        </p>
      ) : threads.error && listed.length === 0 ? (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void threads.refetch()}>
              Try again
            </Button>
          }
        >
          Could not load the discussions. {describeError(threads.error)}
        </Banner>
      ) : listed.length === 0 ? (
        <EmptyState title="No discussions yet">
          {filter === 'resolved'
            ? 'Resolved discussions appear here.'
            : 'Start one to keep talk about this item in one place.'}
        </EmptyState>
      ) : (
        <ul aria-label="Discussions" className="m-0 flex list-none flex-col gap-3 p-0">
          {listed.map((thread) => (
            <li key={thread.id}>
              <ThreadCard
                projectId={projectId}
                thread={thread}
                userId={user?.id ?? null}
                resolvesAny={resolvesAny}
                showAbout={scope.kind === 'project'}
                versionLabel={versionLabel}
                focusCommentId={focusCommentId}
                onPosted={setFocusCommentId}
              />
            </li>
          ))}
        </ul>
      )}
      {threads.hasNextPage && (
        <Button onClick={() => void threads.fetchNextPage()} disabled={threads.isFetchingNextPage}>
          {threads.isFetchingNextPage ? 'Loading…' : 'Show older discussions'}
        </Button>
      )}
    </div>
  );
}
