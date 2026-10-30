import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { CommentItem } from './CommentItem';
import { Composer } from './Composer';
import { aboutLabel } from './types';
import type { Thread } from './types';
import { discussionsKey, useDiscussionCommands } from './useDiscussions';

interface ThreadCardProps {
  projectId: string;
  thread: Thread;
  userId: string | null;
  /** Editors and approvers may resolve anyone's thread; anyone may resolve their own. */
  resolvesAny: boolean;
  /** Names the item or General discussion, where threads of several are listed together. */
  showAbout: boolean;
  versionLabel: (versionId: string | null) => string | null;
  /** The comment to move focus to once it renders, e.g. the one just posted. */
  focusCommentId: string | null;
  onPosted: (commentId: string) => void;
}

export function ThreadCard({
  projectId,
  thread,
  userId,
  resolvesAny,
  showAbout,
  versionLabel,
  focusCommentId,
  onPosted,
}: ThreadCardProps) {
  const resolved = thread.status === 'resolved';
  const [unfolded, setUnfolded] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { run, isPending } = useDiscussionCommands(projectId);
  const queryClient = useQueryClient();
  const [first] = thread.comments;
  const canResolve = resolvesAny || thread.created_by === userId;
  const folded = resolved && !unfolded;
  const stale = error instanceof ApiError && error.status === 409;

  function changeState(type: 'resolve' | 'reopen') {
    setError(null);
    run({ type, threadId: thread.id, expectedRevision: thread.revision }).then(
      () => {
        setUnfolded(false);
      },
      (failure: unknown) => {
        setError(failure instanceof Error ? failure : new Error(String(failure)));
      },
    );
  }

  return (
    <Card className={cx(resolved && 'bg-surface-2')}>
      <div className="flex flex-wrap items-center gap-2">
        {showAbout && (
          <span className="min-w-0 text-xs font-semibold break-words text-muted">
            {aboutLabel(thread)}
          </span>
        )}
        {thread.item && !thread.item.in_current_backlog && (
          <Tag tone="warn">Item no longer in the backlog</Tag>
        )}
        {resolved && (
          <Tag tone="ok">
            <Icon name="check" size={12} />
            Resolved
          </Tag>
        )}
      </div>
      {folded ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 flex-1 truncate text-sm text-muted">
            {first?.deleted ? 'Comment deleted' : first?.body}
          </p>
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={false}
            onClick={() => {
              setUnfolded(true);
            }}
          >
            Show{' '}
            {thread.comments.length === 1
              ? 'comment'
              : `${String(thread.comments.length)} comments`}
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {thread.comments.map((comment) => (
              <li key={comment.id}>
                <CommentItem
                  projectId={projectId}
                  comment={comment}
                  mine={comment.author_id === userId}
                  versionLabel={versionLabel(comment.backlog_version_id)}
                  focusOnMount={comment.id === focusCommentId}
                />
              </li>
            ))}
          </ol>
          {!resolved && (
            <Composer
              projectId={projectId}
              draftKey={`reply:${thread.id}`}
              label="Reply"
              placeholder="Reply…"
              submitLabel="Reply"
              onSubmit={async (body) => {
                const updated = await run({ type: 'reply', threadId: thread.id, body });
                const posted = updated?.comments.at(-1);
                if (posted) {
                  onPosted(posted.id);
                }
              }}
            />
          )}
        </div>
      )}
      {error && (
        <Banner
          tone="bad"
          role="alert"
          action={
            stale ? (
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  void queryClient.invalidateQueries({ queryKey: discussionsKey(projectId) });
                }}
              >
                Reload
              </Button>
            ) : undefined
          }
        >
          {stale
            ? 'Someone changed this discussion since you opened it. Reload to see it as it is now.'
            : describeError(error)}
        </Banner>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        {resolved && unfolded && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded
            onClick={() => {
              setUnfolded(false);
            }}
          >
            Fold
          </Button>
        )}
        {resolved ? (
          <Button
            size="sm"
            disabled={isPending}
            onClick={() => {
              changeState('reopen');
            }}
          >
            Reopen
          </Button>
        ) : (
          canResolve && (
            <Button
              size="sm"
              disabled={isPending}
              onClick={() => {
                changeState('resolve');
              }}
            >
              <Icon name="check" size={14} />
              Resolve
            </Button>
          )
        )}
      </div>
    </Card>
  );
}
