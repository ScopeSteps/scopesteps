import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { ApiError, describeError } from '@/lib/apiError';

import type { DiscussionLinks } from './DiscussionPanel';
import { ThreadCard } from './ThreadCard';
import { useThread } from './useDiscussions';
import { useThreadContext } from './useThreadContext';

interface OpenedThreadProps {
  projectId: string;
  threadId: string;
  /** The comment a notification points at, shown highlighted. */
  commentId: string | null;
  links: DiscussionLinks;
}

/** One thread a link named, resolved or not and however far down the list it is. */
export function OpenedThread({ projectId, threadId, commentId, links }: OpenedThreadProps) {
  const thread = useThread(projectId, threadId);
  const { user, resolvesAny, versionLabel } = useThreadContext(projectId);
  const [focusCommentId, setFocusCommentId] = useState<string | null>(null);

  if (thread.isPending) {
    return (
      <p role="status" className="text-subtle">
        Loading the discussion…
      </p>
    );
  }
  if (thread.error) {
    return (
      <Banner tone="bad" role="alert">
        {thread.error instanceof ApiError && thread.error.status === 404
          ? 'This discussion is no longer available.'
          : `Could not load the discussion. ${describeError(thread.error)}`}
      </Banner>
    );
  }
  return (
    <ThreadCard
      projectId={projectId}
      thread={thread.data}
      userId={user?.id ?? null}
      resolvesAny={resolvesAny}
      showAbout
      versionLabel={versionLabel}
      focusCommentId={focusCommentId}
      onPosted={setFocusCommentId}
      highlightCommentId={commentId}
      links={links}
    />
  );
}
