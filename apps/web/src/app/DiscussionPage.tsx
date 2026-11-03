import { Link, useParams, useSearchParams } from 'react-router';

import {
  COMMENT_PARAM,
  changeRequestPath,
  discussionPath,
  requestChangePath,
  THREAD_PARAM,
} from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { DiscussionPanel, OpenedThread } from '@/features/discussions';

/** General discussion and every thread in the project, for talk outside meetings. */
export function DiscussionPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  if (!projectId) {
    return null;
  }
  const threadId = searchParams.get(THREAD_PARAM);
  const links = {
    requestChangeHref: (id: string) => requestChangePath(projectId, id),
    changeRequestHref: (id: string) => changeRequestPath(projectId, id),
  };

  return (
    <PageBody>
      <p className="text-muted">
        Ideas and questions about scope, written down where the whole team can see them. A
        discussion never changes the backlog.
      </p>
      {threadId ? (
        <>
          {/* Keyed so opening another notification starts from its own comment. */}
          <OpenedThread
            key={`${threadId}:${searchParams.get(COMMENT_PARAM) ?? ''}`}
            projectId={projectId}
            threadId={threadId}
            commentId={searchParams.get(COMMENT_PARAM)}
            links={links}
          />
          <Link to={discussionPath(projectId)} className="text-[13px] text-accent-ink underline">
            Show all discussions
          </Link>
        </>
      ) : (
        <DiscussionPanel projectId={projectId} scope={{ kind: 'project' }} links={links} />
      )}
    </PageBody>
  );
}
