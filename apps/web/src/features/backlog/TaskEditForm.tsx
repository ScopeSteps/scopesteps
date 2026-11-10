import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { IconButton } from '@/components/IconButton';
import { TextField } from '@/components/TextField';
import { describeError } from '@/lib/apiError';

import { isPendingTask, MAX_TASK_TITLE, MAX_TASKS } from './types';
import type { BacklogItem, ItemPatch } from './types';

interface DraftTask {
  /** The task's id, or a local key for one added in this form. */
  key: string;
  id: string | null;
  title: string;
  isSuggestion: boolean;
}

interface TaskEditFormProps {
  story: BacklogItem;
  saving: boolean;
  /** The page is out of date, so saving would be refused. */
  locked: boolean;
  /** A failed save, other than a stale revision, which the page reports. */
  error: Error | null;
  onSave: (patch: ItemPatch) => void;
  onCancel: () => void;
}

/** The form's list as the API's whole new list of tasks, in order; a task left out is deleted. */
function tasksPatch(tasks: readonly DraftTask[]): ItemPatch {
  return {
    tasks: tasks.map((task) => ({ id: task.id, title: task.title.trim(), accept: false })),
  };
}

function move<T>(list: readonly T[], from: number, to: number): T[] {
  const next = [...list];
  const [moved] = next.splice(from, 1);
  if (moved !== undefined) {
    next.splice(to, 0, moved);
  }
  return next;
}

/** Adds, rewords, reorders and deletes a story's tasks, saved as one edit. */
export function TaskEditForm({
  story,
  saving,
  locked,
  error,
  onSave,
  onCancel,
}: TaskEditFormProps) {
  const [tasks, setTasks] = useState<DraftTask[]>(() =>
    story.tasks
      .filter((task) => task.suggestion !== 'rejected')
      .map((task) => ({
        key: task.id,
        id: task.id,
        title: task.title,
        isSuggestion: isPendingTask(task),
      })),
  );
  const [showProblems, setShowProblems] = useState(false);
  const blank = new Set(tasks.filter((task) => !task.title.trim()).map((task) => task.key));

  function update(key: string, title: string) {
    setTasks((current) => current.map((task) => (task.key === key ? { ...task, title } : task)));
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blank.size > 0) {
      setShowProblems(true);
      return;
    }
    onSave(tasksPatch(tasks));
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={`Edit tasks: ${story.title}`}
      className="flex flex-col gap-3"
    >
      {tasks.length === 0 && (
        <p className="text-xs text-subtle">No tasks. Add the steps the team takes to build it.</p>
      )}
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {tasks.map((task, index) => {
          const position = String(index + 1);
          return (
            <li key={task.key} className="flex items-start gap-1">
              <div className="min-w-0 flex-1">
                <TextField
                  label={`Task ${position}`}
                  value={task.title}
                  onChange={(title) => {
                    update(task.key, title);
                  }}
                  maxLength={MAX_TASK_TITLE}
                  disabled={saving}
                  help={
                    task.isSuggestion
                      ? 'Suggested by AI. Changing its wording accepts it.'
                      : task.id === null
                        ? 'Added by you'
                        : undefined
                  }
                  error={showProblems && blank.has(task.key) ? 'Enter the task.' : null}
                  focusOnMount={task.id === null}
                />
              </div>
              <div className="mt-6 flex flex-none">
                <IconButton
                  icon="up"
                  label={`Move task ${position} up`}
                  disabled={saving || index === 0}
                  onClick={() => {
                    setTasks((current) => move(current, index, index - 1));
                  }}
                />
                <IconButton
                  icon="more"
                  label={`Move task ${position} down`}
                  disabled={saving || index === tasks.length - 1}
                  onClick={() => {
                    setTasks((current) => move(current, index, index + 1));
                  }}
                />
                <IconButton
                  icon="close"
                  label={`Delete task ${position}`}
                  disabled={saving}
                  onClick={() => {
                    setTasks((current) => current.filter((other) => other.key !== task.key));
                  }}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <Button
        size="sm"
        variant="ghost"
        className="self-start text-accent-ink"
        disabled={saving || tasks.length >= MAX_TASKS}
        onClick={() => {
          setTasks((current) => [
            ...current,
            { key: crypto.randomUUID(), id: null, title: '', isSuggestion: false },
          ]);
        }}
      >
        + Add task
      </Button>
      {tasks.length >= MAX_TASKS && (
        <p className="text-xs text-subtle">
          This story has as many tasks as it can hold. Delete one to add another.
        </p>
      )}
      {error && (
        <Banner tone="bad" role="alert">
          The tasks were not saved. {describeError(error)}
        </Banner>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={saving || locked}>
          {saving ? 'Saving…' : 'Save tasks'}
        </Button>
        <Button size="sm" disabled={saving} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
