import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { ApiError, describeError } from '@/lib/apiError';

import { KIND_LABELS } from './types';
import type { SourceKind, SourceVersion } from './types';
import { useUploadSources } from './useUploadSources';

const ACCEPTED_FILES = '.txt,.md,.markdown,text/plain,text/markdown';
const KINDS: SourceKind[] = ['brief', 'transcript'];

interface SourceUploadFormProps {
  projectId: string;
  onUploaded?: (versions: SourceVersion[]) => void;
}

function rejectedField(error: Error | null): SourceKind | null {
  const field = error instanceof ApiError ? error.details.field : null;
  return field === 'brief' || field === 'transcript' ? field : null;
}

export function SourceUploadForm({ projectId, onUploaded }: SourceUploadFormProps) {
  const upload = useUploadSources(projectId);
  const [files, setFiles] = useState<Record<SourceKind, File | null>>({
    brief: null,
    transcript: null,
  });
  const [missingFiles, setMissingFiles] = useState(false);
  // One key per attempt whose outcome is unknown: kept across a retry after a network or
  // server failure, replaced once the API has given a definite answer or the files change.
  const idempotencyKey = useRef<string | null>(null);
  const errorId = useId();
  const inputIdPrefix = useId();

  const invalidField = rejectedField(upload.error);

  function chooseFile(kind: SourceKind, file: File | null) {
    setFiles((current) => ({ ...current, [kind]: file }));
    setMissingFiles(false);
    idempotencyKey.current = null;
    upload.reset();
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const { brief, transcript } = files;
    if (!brief || !transcript) {
      setMissingFiles(true);
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    upload.mutate(
      { brief, transcript, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (versions) => {
          idempotencyKey.current = null;
          form.reset();
          setFiles({ brief: null, transcript: null });
          onUploaded?.(versions);
        },
        onError: (error) => {
          if (error instanceof ApiError && !error.retryable) {
            idempotencyKey.current = null;
          }
        },
      },
    );
  }

  const errorMessage = missingFiles
    ? 'Choose both a project brief and a meeting transcript.'
    : upload.error
      ? describeError(upload.error)
      : null;

  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${inputIdPrefix}-heading`}>
      <h2 id={`${inputIdPrefix}-heading`} className="text-lg font-semibold">
        Upload sources
      </h2>
      <p className="mt-1 text-sm text-muted">
        UTF-8 text or Markdown (.txt, .md), up to 512 KiB each and 6,000 words in total. Both
        documents are stored together or not at all.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {KINDS.map((kind) => {
          const inputId = `${inputIdPrefix}-${kind}`;
          const isInvalid = invalidField === kind || (missingFiles && !files[kind]);
          return (
            <div key={kind}>
              <label htmlFor={inputId} className="block text-sm font-medium">
                {KIND_LABELS[kind]}
              </label>
              <input
                id={inputId}
                type="file"
                accept={ACCEPTED_FILES}
                aria-invalid={isInvalid}
                aria-describedby={isInvalid ? errorId : undefined}
                disabled={upload.isPending}
                onChange={(event) => {
                  chooseFile(kind, event.currentTarget.files?.[0] ?? null);
                }}
                className="mt-1 block w-full rounded border border-line p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-hover file:px-3 file:py-1 aria-invalid:border-bad-line"
              />
            </div>
          );
        })}
      </div>

      <button
        type="submit"
        disabled={upload.isPending}
        className="mt-4 rounded bg-accent px-4 py-2 text-sm font-medium text-accent-fg hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60"
      >
        {upload.isPending ? 'Uploading…' : 'Upload sources'}
      </button>

      {errorMessage && (
        <p id={errorId} role="alert" className="mt-3 text-sm text-bad-ink">
          {errorMessage}
        </p>
      )}
      <p role="status" className="mt-3 text-sm text-ok-ink">
        {upload.isPending && 'Uploading sources…'}
        {upload.isSuccess &&
          `Stored ${upload.data
            .map((version) => `${version.filename} (version ${String(version.version)})`)
            .join(' and ')}.`}
      </p>
    </form>
  );
}
