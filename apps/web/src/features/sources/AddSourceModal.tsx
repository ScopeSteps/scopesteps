import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { Select } from '@/components/Select';
import { useToast } from '@/components/toastContext';
import { useProject } from '@/features/projects';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { ACCEPTED_SOURCE_FILES, checkSourceFile } from './checkSourceFile';
import { formatBytes } from './format';
import { KIND_LABELS, SOURCE_KINDS, sourceLabel } from './types';
import type { SourceKind, SourceVersion } from './types';
import { useSources } from './useSources';
import { useUploadSources } from './useUploadSources';

interface AddSourceModalProps {
  projectId: string;
  onClose: () => void;
}

/** A project usually starts from a brief and a transcript; anything after is supporting. */
function suggestedKind(current: readonly SourceVersion[] | undefined): SourceKind {
  const held = new Set(current?.map((version) => version.kind));
  if (!held.has('brief')) {
    return 'brief';
  }
  return held.has('transcript') ? 'supporting_document' : 'transcript';
}

function storedMessage(stored: SourceVersion, current: readonly SourceVersion[] | undefined) {
  const label = `${sourceLabel(stored.source_number)} ${stored.filename}`;
  // The API answers an identical file with the version it already holds.
  return current?.some((version) => version.id === stored.id)
    ? `${label} is already stored with the same content.`
    : `${label} added. The agent uses it from the next run.`;
}

/** Uploads one file as a new source of the kind chosen. */
export function AddSourceModal({ projectId, onClose }: AddSourceModalProps) {
  const upload = useUploadSources(projectId);
  const { data: project } = useProject(projectId);
  const { data: current } = useSources(projectId);
  const showToast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [chosenKind, setChosenKind] = useState<SourceKind | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // One key per attempt whose outcome is unknown: kept across a retry after a network or
  // server failure, replaced once the API has given a definite answer or the file changes.
  const idempotencyKey = useRef<string | null>(null);
  const formId = useId();
  const fileInputId = useId();
  const kindId = useId();
  const errorId = useId();

  const limits = project?.limits.source;
  const kind = chosenKind ?? suggestedKind(current);

  function startOver() {
    idempotencyKey.current = null;
    upload.reset();
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setProblem('Choose a file to add.');
      return;
    }
    const refusal = checkSourceFile(file, limits);
    if (refusal) {
      setProblem(refusal);
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    upload.mutate(
      { files: [{ kind, file }], idempotencyKey: idempotencyKey.current },
      {
        onSuccess: ([stored]) => {
          idempotencyKey.current = null;
          if (stored) {
            showToast(storedMessage(stored, current));
          }
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

  const errorMessage = problem ?? (upload.error ? describeError(upload.error) : null);

  return (
    <Modal
      title="Add a source"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form={formId} variant="primary" disabled={upload.isPending}>
            {upload.isPending ? 'Adding…' : 'Add source'}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={kindId} className="text-[13px] font-semibold">
            Type
          </label>
          <Select
            id={kindId}
            value={kind}
            disabled={upload.isPending}
            onChange={(event) => {
              const value = SOURCE_KINDS.find((option) => option === event.currentTarget.value);
              if (value) {
                setChosenKind(value);
                startOver();
              }
            }}
            className="self-start"
          >
            {SOURCE_KINDS.map((option) => (
              <option key={option} value={option}>
                {KIND_LABELS[option]}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed border-line-strong p-[18px]">
          <label htmlFor={fileInputId} className="text-[13px] font-semibold">
            Upload a .txt or .md file
          </label>
          <input
            id={fileInputId}
            type="file"
            accept={ACCEPTED_SOURCE_FILES}
            aria-invalid={errorMessage !== null}
            aria-describedby={errorMessage !== null ? errorId : undefined}
            disabled={upload.isPending}
            onChange={(event) => {
              const chosen = event.currentTarget.files?.[0] ?? null;
              setFile(chosen);
              setProblem(chosen ? checkSourceFile(chosen, limits) : null);
              startOver();
            }}
            className={cx(
              'w-full rounded-lg border bg-surface p-2 text-[13px] file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-hover file:px-3 file:py-1 file:text-fg',
              errorMessage !== null ? 'border-bad-line' : 'border-line',
            )}
          />
          <span className="text-xs text-subtle">
            {limits
              ? `Up to ${formatBytes(limits.max_bytes)} per file and ${limits.max_words.toLocaleString()} words across all sources. `
              : 'TXT or Markdown. '}
            Paragraphs are numbered so the agent can cite them.
          </span>
          {errorMessage !== null && (
            <p id={errorId} role="alert" className="text-[13px] text-bad-ink">
              {errorMessage}
            </p>
          )}
          {upload.isPending && (
            <p role="status" className="text-[13px] text-muted">
              Adding the source…
            </p>
          )}
        </div>
      </form>
    </Modal>
  );
}
