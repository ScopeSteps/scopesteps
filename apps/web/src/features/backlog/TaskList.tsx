import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { JiraKeyLink } from '@/features/jira';
import type { JiraLinks } from '@/features/jira';
import { cx } from '@/lib/cx';

import { isPendingTask } from './types';
import type { StoryTask } from './types';

interface TaskListProps {
  storyTitle: string;
  tasks: readonly StoryTask[];
  /** Accepts or deletes a suggested task; absent when the reader cannot change tasks. */
  onReview?: ((taskId: string, outcome: 'accept' | 'delete') => void) | undefined;
  busy?: boolean;
  /** Each task's Jira issue, once published. */
  jiraLinks?: JiraLinks | undefined;
}

function TaskTags({ task }: { task: StoryTask }) {
  if (task.origin !== 'suggested') {
    return null;
  }
  return isPendingTask(task) ? (
    <Tag tone="warn">Suggested by AI</Tag>
  ) : (
    <Tag>Suggested by AI · accepted</Tag>
  );
}

/** A story's tasks in the order the team does them, with the review of each AI suggestion. */
export function TaskList({ storyTitle, tasks, onReview, busy = false, jiraLinks }: TaskListProps) {
  return (
    <ol aria-label={`Tasks for ${storyTitle}`} className="m-0 flex list-none flex-col gap-1.5 p-0">
      {tasks.map((task, index) => {
        const pending = isPendingTask(task);
        const jira = jiraLinks?.[task.id];
        return (
          <li
            key={task.id}
            className={cx(
              'flex flex-col gap-1.5 rounded-lg border px-3 py-2 text-sm',
              pending ? 'border-dashed border-warn-line bg-warn-soft' : 'border-line bg-surface-2',
            )}
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-xs text-subtle tabular-nums">{index + 1}.</span>
              <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{task.title}</span>
              <TaskTags task={task} />
              {jira && <JiraKeyLink link={jira} />}
            </div>
            {task.flag && (
              <p className="flex items-start gap-1.5 text-xs text-warn-ink">
                <span aria-hidden="true" className="mt-px flex-none">
                  <Icon name="warn" size={14} />
                </span>
                <span>
                  <span className="font-semibold">Check this task:</span> {task.flag.message}
                </span>
              </p>
            )}
            {pending && onReview && (
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy}
                  aria-label={`Accept task: ${task.title}`}
                  onClick={() => {
                    onReview(task.id, 'accept');
                  }}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  disabled={busy}
                  aria-label={`Delete task: ${task.title}`}
                  onClick={() => {
                    onReview(task.id, 'delete');
                  }}
                >
                  Delete
                </Button>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
