import { useReviewerName } from '@/features/identity';

import type { Message } from './types';

/** The author as the project names them now, or as they were named when they wrote it. */
export function useAuthorName(projectId: string) {
  const reviewerName = useReviewerName(projectId);
  return (author: Message['author']) => {
    if (!author) {
      return 'Someone';
    }
    const now = reviewerName(author.user_id);
    return ['a former member', 'a reviewer', 'an unknown reviewer'].includes(now)
      ? author.display_name
      : now;
  };
}
