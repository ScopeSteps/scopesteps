import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import type { TaskSuggestions } from './types';

function forStories(storyIds: readonly string[] | null): string {
  if (storyIds === null) {
    return 'the stories';
  }
  return storyIds.length === 1 ? 'this story' : `${String(storyIds.length)} stories`;
}

/** How the agent's task suggestions are going: working, failed, or ready to review. */
export function TaskSuggestionStatus({ suggestions }: { suggestions: TaskSuggestions }) {
  const { busy, storyIds, finished, error, retry, dismiss } = suggestions;
  if (error) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <span className="flex gap-2">
            {retry && (
              <Button size="sm" onClick={retry}>
                Try again
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={dismiss}>
              Dismiss
            </Button>
          </span>
        }
      >
        The agent could not suggest tasks. {describeError(error)}
      </Banner>
    );
  }
  if (busy) {
    return (
      <Banner role="status">
        Suggesting tasks for {forStories(storyIds)}… They appear under each story as they are ready.
      </Banner>
    );
  }
  if (finished) {
    return (
      <Banner
        role="status"
        action={
          <Button size="sm" variant="ghost" onClick={dismiss}>
            Dismiss
          </Button>
        }
      >
        Suggested tasks are ready. Accept, reword or delete each one marked “Suggested by AI” before
        approving.
      </Banner>
    );
  }
  return null;
}
