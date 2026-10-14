import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { describeError } from '@/lib/apiError';

import { suggestionStatus } from './types';
import type { BacklogItem, CriterionPatch, ItemPatch } from './types';

// The API's limits on an item edit (ItemPatchRequest and CriterionPatch).
const MAX_TITLE = 200;
const MAX_DESCRIPTION = 4000;
const MAX_CRITERION = 1000;
const MAX_CRITERIA = 30;

interface DraftCriterion {
  /** The criterion's id, or a local key for one added in this form. */
  key: string;
  id: string | null;
  text: string;
  isSuggestion: boolean;
}

interface StoryEditFormProps {
  story: BacklogItem;
  saving: boolean;
  /** The page is out of date, so saving would be refused. */
  locked: boolean;
  /** A failed save, other than a stale revision, which the page reports. */
  error: Error | null;
  onSave: (patch: ItemPatch) => void;
  onCancel: () => void;
}

function toPatch(
  title: string,
  description: string,
  criteria: DraftCriterion[],
  story: BacklogItem,
): ItemPatch {
  // Rejected suggestions are not shown, but stay on the item so they can be reopened.
  const rejected: CriterionPatch[] = story.criteria
    .filter((criterion) => suggestionStatus(criterion) === 'rejected')
    .map((criterion) => ({ id: criterion.id, text: criterion.text, suggestion: null }));
  return {
    title: title.trim(),
    description: description.trim(),
    criteria: [
      ...criteria.map((criterion) => ({
        id: criterion.id,
        text: criterion.text.trim(),
        suggestion: null,
      })),
      ...rejected,
    ],
  };
}

/** Edits a story's title, text and criteria, and adds criteria, saved as one edit. */
export function StoryEditForm({
  story,
  saving,
  locked,
  error,
  onSave,
  onCancel,
}: StoryEditFormProps) {
  const [title, setTitle] = useState(story.title);
  const [description, setDescription] = useState(story.description);
  const [criteria, setCriteria] = useState<DraftCriterion[]>(() =>
    story.criteria
      .filter((criterion) => suggestionStatus(criterion) !== 'rejected')
      .map((criterion) => ({
        key: criterion.id,
        id: criterion.id,
        text: criterion.text,
        isSuggestion: suggestionStatus(criterion) === 'pending',
      })),
  );
  const [showProblems, setShowProblems] = useState(false);
  const titleProblem = title.trim() ? null : 'Enter a title.';
  const blank = new Set(
    criteria.filter((criterion) => !criterion.text.trim()).map((criterion) => criterion.key),
  );
  const rejectedCount = story.criteria.filter(
    (criterion) => suggestionStatus(criterion) === 'rejected',
  ).length;
  const atLimit = criteria.length + rejectedCount >= MAX_CRITERIA;

  function update(key: string, text: string) {
    setCriteria((current) =>
      current.map((criterion) => (criterion.key === key ? { ...criterion, text } : criterion)),
    );
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (titleProblem || blank.size > 0) {
      setShowProblems(true);
      return;
    }
    onSave(toPatch(title, description, criteria, story));
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label={`Edit story: ${story.title}`}
      className="flex flex-col gap-3"
    >
      <TextField
        label="Title"
        value={title}
        onChange={setTitle}
        maxLength={MAX_TITLE}
        disabled={saving}
        error={showProblems ? titleProblem : null}
        focusOnMount
      />
      <TextField
        label="Story"
        value={description}
        onChange={setDescription}
        rows={3}
        maxLength={MAX_DESCRIPTION}
        disabled={saving}
      />
      {criteria.map((criterion, index) => (
        <div key={criterion.key} className="flex flex-col gap-1">
          <TextField
            label={`Acceptance criterion ${String(index + 1)}`}
            value={criterion.text}
            onChange={(text) => {
              update(criterion.key, text);
            }}
            rows={2}
            maxLength={MAX_CRITERION}
            disabled={saving}
            help={
              criterion.isSuggestion
                ? 'Agent suggestion. Changing its text accepts it.'
                : criterion.id === null
                  ? 'Added by you'
                  : undefined
            }
            error={showProblems && blank.has(criterion.key) ? 'Enter the criterion.' : null}
            focusOnMount={criterion.id === null}
          />
          {criterion.id === null && (
            <Button
              size="sm"
              variant="ghost"
              className="self-start"
              disabled={saving}
              onClick={() => {
                setCriteria((current) => current.filter((other) => other.key !== criterion.key));
              }}
            >
              Remove new criterion {index + 1}
            </Button>
          )}
        </div>
      ))}
      <Button
        size="sm"
        variant="ghost"
        className="self-start text-accent-ink"
        disabled={saving || atLimit}
        onClick={() => {
          setCriteria((current) => [
            ...current,
            { key: crypto.randomUUID(), id: null, text: '', isSuggestion: false },
          ]);
        }}
      >
        + Add acceptance criterion
      </Button>
      {error && (
        <Banner tone="bad" role="alert">
          The story was not saved. {describeError(error)}
        </Banner>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={saving || locked}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
        <Button size="sm" disabled={saving} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
