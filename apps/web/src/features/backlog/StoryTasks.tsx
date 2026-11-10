import { useState } from 'react';

import { Button } from '@/components/Button';

import { errorFor, isLocked, isSaving } from './draftControls';
import type { DraftControls } from './draftControls';
import { TaskEditForm } from './TaskEditForm';
import { TaskList } from './TaskList';
import { acceptTask, deleteTask, shownTasks } from './types';
import type { BacklogItem, TaskSuggestions } from './types';

interface StoryTasksProps {
  story: BacklogItem;
  /** The draft's controls, or null when the version or the reader's role is read-only. */
  draft: DraftControls | null;
  /** Suggesting tasks with the agent; absent where nobody can start it from this page. */
  suggestions?: TaskSuggestions | undefined;
  /** Keeps the story open after the reviewer acts in it. */
  onKeepOpen: () => void;
}

/** A story's tasks, and for an editor of a draft: suggest, review, add, edit and reorder them. */
export function StoryTasks({ story, draft, suggestions, onKeepOpen }: StoryTasksProps) {
  const [editing, setEditing] = useState(false);
  const tasks = shownTasks(story);
  const canChange = draft?.canEdit === true;
  const target = `item:${story.id}`;
  const locked = draft ? isLocked(draft) : true;
  // A run saving suggestions would be overwritten by an edit sent from what the page showed.
  const agentWorking = suggestions?.busy === true;
  const working =
    agentWorking && (suggestions.storyIds === null || suggestions.storyIds.includes(story.id));

  if (editing && canChange) {
    return (
      <section aria-label={`Tasks for ${story.title}`} className="flex flex-col gap-2">
        <h6 className="text-xs font-semibold text-subtle">Tasks</h6>
        <TaskEditForm
          story={story}
          saving={isSaving(draft, target)}
          locked={locked || agentWorking}
          error={errorFor(draft, target)}
          onSave={(patch) => {
            onKeepOpen();
            draft.commands.send({ type: 'edit', itemId: story.id, patch }, () => {
              setEditing(false);
            });
          }}
          onCancel={() => {
            draft.commands.reset();
            setEditing(false);
          }}
        />
      </section>
    );
  }

  if (tasks.length === 0 && !canChange) {
    return null;
  }

  return (
    <section aria-label={`Tasks for ${story.title}`} className="flex flex-col gap-1.5">
      <h6 className="text-xs font-semibold text-subtle">
        Tasks{tasks.length > 0 && ` (${String(tasks.length)})`}
      </h6>
      {tasks.length === 0 && (
        <p className="text-xs text-subtle">
          No tasks yet. Ask the agent to suggest some, or add your own.
        </p>
      )}
      {tasks.length > 0 && (
        <TaskList
          storyTitle={story.title}
          tasks={tasks}
          busy={locked || agentWorking}
          onReview={
            canChange
              ? (taskId, outcome) => {
                  onKeepOpen();
                  draft.commands.send({
                    type: 'edit',
                    itemId: story.id,
                    patch:
                      outcome === 'accept' ? acceptTask(story, taskId) : deleteTask(story, taskId),
                  });
                }
              : undefined
          }
        />
      )}
      {working && (
        <p role="status" className="text-xs text-subtle">
          The agent is suggesting tasks for this story…
        </p>
      )}
      {canChange && (
        <div className="flex flex-wrap gap-2">
          {suggestions && (
            <Button
              size="sm"
              variant="ghost"
              disabled={locked || agentWorking}
              aria-label={`Suggest tasks: ${story.title}`}
              onClick={() => {
                onKeepOpen();
                suggestions.suggest([story.id]);
              }}
            >
              Suggest tasks
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            disabled={locked || agentWorking}
            aria-label={`${tasks.length === 0 ? 'Add tasks' : 'Edit tasks'}: ${story.title}`}
            onClick={() => {
              draft.commands.reset();
              setEditing(true);
            }}
          >
            {tasks.length === 0 ? 'Add tasks' : 'Edit tasks'}
          </Button>
        </div>
      )}
    </section>
  );
}
