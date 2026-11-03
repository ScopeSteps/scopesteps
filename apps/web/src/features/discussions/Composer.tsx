import { useState } from 'react';
import type { KeyboardEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import { loadDraft, saveDraft } from './drafts';
import { EMPTY_MENTION_TEXT, encodeMentions } from './mentions';
import type { MentionText } from './mentions';
import { MentionInput } from './MentionInput';

interface ComposerProps {
  projectId: string;
  /** Which box this is, so its unsent text comes back when the panel is opened again. */
  draftKey: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  onSubmit: (body: string) => Promise<unknown>;
  disabled?: boolean;
}

/** A plain-text box with @mentions that posts on its button or Cmd/Ctrl+Enter. */
export function Composer({
  projectId,
  draftKey,
  label,
  placeholder,
  submitLabel,
  onSubmit,
  disabled = false,
}: ComposerProps) {
  const [value, setValue] = useState(() => loadDraft(projectId, draftKey));
  const [error, setError] = useState<Error | null>(null);
  const [posting, setPosting] = useState(false);
  const empty = value.text.trim() === '';

  function change(next: MentionText) {
    setValue(next);
    saveDraft(projectId, draftKey, next);
  }

  function post() {
    if (posting || disabled || empty) {
      return;
    }
    setPosting(true);
    setError(null);
    onSubmit(encodeMentions(value)).then(
      () => {
        change(EMPTY_MENTION_TEXT);
        setPosting(false);
      },
      (failure: unknown) => {
        setError(failure instanceof Error ? failure : new Error(String(failure)));
        setPosting(false);
      },
    );
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      post();
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <MentionInput
        projectId={projectId}
        label={label}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={change}
        onKeyDown={onKeyDown}
      />
      {error && (
        <Banner tone="bad" role="alert">
          {describeError(error)}
        </Banner>
      )}
      <div className="flex justify-end">
        <Button size="sm" variant="primary" disabled={disabled || posting || empty} onClick={post}>
          {posting ? 'Posting…' : submitLabel}
        </Button>
      </div>
    </div>
  );
}
