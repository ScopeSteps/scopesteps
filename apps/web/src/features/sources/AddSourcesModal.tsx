import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/toastContext';
import { useProject } from '@/features/projects';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { formatBytes } from './format';
import { KIND_LABELS } from './types';
import type { SourceVersion } from './types';
import { useUploadSources } from './useUploadSources';

const ACCEPTED_FILES = '.txt,.md,.markdown,text/plain,text/markdown';
// This form uploads a brief and a transcript together; adding one file of any kind is a later
// screen. The API accepts any combination.
type UploadKind = 'brief' | 'transcript';
const KINDS: UploadKind[] = ['brief', 'transcript'];

interface AddSourcesModalProps {
  projectId: string;
  onClose: () => void;
}

function rejectedField(error: Error | null): UploadKind | null {
  const field = error instanceof ApiError ? error.details.field : null;
  return field === 'brief' || field === 'transcript' ? field : null;
}

function storedMessage(versions: SourceVersion[]): string {
  return `Stored ${versions
    .map((version) => `${version.filename} (version ${String(version.version)})`)
    .join(' and ')}.`;
}

/** Uploads a brief and a transcript in one command: the API stores both or neither. */
export function AddSourcesModal({ projectId, onClose }: AddSourcesModalProps) {
  const upload = useUploadSources(projectId);
  const { data: project } = useProject(projectId);
  const showToast = useToast();
  const [files, setFiles] = useState<Record<UploadKind, File | null>>({
    brief: null,
    transcript: null,
  });
  const [missingFiles, setMissingFiles] = useState(false);
  // One key per attempt whose outcome is unknown: kept across a retry after a network or
  // server failure, replaced once the API has given a definite answer or the files change.
  const idempotencyKey = useRef<string | null>(null);
  const formId = useId();
  const errorId = useId();

  const invalidField = rejectedField(upload.error);
  const limits = project?.limits.source;

  function chooseFile(kind: UploadKind, file: File | null) {
    setFiles((current) => ({ ...current, [kind]: file }));
    setMissingFiles(false);
    idempotencyKey.current = null;
    upload.reset();
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
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
          showToast(storedMessage(versions));
          onClose();
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
    <Modal
      title="Add sources"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form={formId} variant="primary" disabled={upload.isPending}>
            {upload.isPending ? 'Uploading…' : 'Upload sources'}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <p className="text-muted">
          Upload a project brief and a meeting transcript together. Both are stored, or neither.
        </p>
        <div className="flex flex-col gap-3 rounded-xl border border-dashed border-line-strong p-[18px]">
          {KINDS.map((kind) => {
            const inputId = `${formId}-${kind}`;
            const isInvalid = invalidField === kind || (missingFiles && !files[kind]);
            return (
              <div key={kind} className="flex flex-col gap-1.5">
                <label htmlFor={inputId} className="text-[13px] font-semibold">
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
                  className={cx(
                    'w-full rounded-lg border bg-surface p-2 text-[13px] file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-hover file:px-3 file:py-1 file:text-fg',
                    isInvalid ? 'border-bad-line' : 'border-line',
                  )}
                />
              </div>
            );
          })}
          <span className="text-xs text-subtle">
            {limits
              ? `TXT or Markdown, up to ${formatBytes(limits.max_bytes)} per file and ${limits.max_words.toLocaleString()} words across both. `
              : 'TXT or Markdown. '}
            Paragraphs are numbered so the agent can cite them.
          </span>
          {errorMessage && (
            <p id={errorId} role="alert" className="text-[13px] text-bad-ink">
              {errorMessage}
            </p>
          )}
          {upload.isPending && (
            <p role="status" className="text-[13px] text-muted">
              Uploading sources…
            </p>
          )}
        </div>
      </form>
    </Modal>
  );
}
