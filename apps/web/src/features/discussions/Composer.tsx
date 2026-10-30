import { useState } from 'react';
import type { KeyboardEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import { loadDraft, saveDraft } from './drafts';

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

/** A plain-text box that posts on its button or Cmd/Ctrl+Enter. */
export function Composer({
  projectId,
  draftKey,
  label,
  placeholder,
  submitLabel,
  onSubmit,
  disabled = false,
}: ComposerProps) {
  const [text, setText] = useState(() => loadDraft(projectId, draftKey));
  const [error, setError] = useState<Error | null>(null);
  const [posting, setPosting] = useState(false);
  const empty = text.trim() === '';

  function change(next: string) {
    setText(next);
    saveDraft(projectId, draftKey, next);
  }

  function post() {
    if (posting || disabled || empty) {
      return;
    }
    setPosting(true);
    setError(null);
    onSubmit(text).then(
      () => {
        change('');
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
      <textarea
        aria-label={label}
        value={text}
        rows={3}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => {
          change(event.target.value);
        }}
        onKeyDown={onKeyDown}
        className="w-full resize-y rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-fg focus:border-accent focus:shadow-focus focus:outline-none disabled:bg-surface-2"
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
