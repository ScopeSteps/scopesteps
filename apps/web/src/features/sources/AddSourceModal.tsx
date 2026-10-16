import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/toastContext';
import { useProject } from '@/features/projects';
import { ApiError, describeError } from '@/lib/apiError';

import { joinList, plural } from './format';
import { SourceFilesPicker } from './SourceFilesPicker';
import { sourceLabel } from './types';
import type { SourceFile, SourceVersion } from './types';
import { useSources } from './useSources';
import { useUploadSources } from './useUploadSources';

interface AddSourceModalProps {
  projectId: string;
  onClose: () => void;
  /** The versions the upload stored as new, after the modal closes. */
  onAdded?: (added: SourceVersion[]) => void;
}

/** The versions the upload stored as new; the API answers an identical file with the one it holds. */
function newlyAdded(
  stored: readonly SourceVersion[],
  current: readonly SourceVersion[] | undefined,
): SourceVersion[] {
  return stored.filter(
    (version, index) =>
      stored.findIndex((other) => other.id === version.id) === index &&
      !current?.some((held) => held.id === version.id),
  );
}

/** What the upload changed. */
function describeStored(
  stored: readonly SourceVersion[],
  current: readonly SourceVersion[] | undefined,
): string {
  const added = newlyAdded(stored, current);
  const kept = stored.filter(
    (version, index) =>
      stored.findIndex((other) => other.id === version.id) === index && !added.includes(version),
  );
  const name = (version: SourceVersion) =>
    `${sourceLabel(version.source_number)} ${version.filename}`;

  const sentences: string[] = [];
  if (added.length > 0) {
    sentences.push(
      `${joinList(added.map(name))} added. The agent uses ${added.length === 1 ? 'it' : 'them'} from the next run.`,
    );
  }
  if (kept.length > 0) {
    sentences.push(
      `${joinList(kept.map(name))} ${kept.length === 1 ? 'is' : 'are'} already stored with the same content.`,
    );
  }
  return sentences.join(' ');
}

/** Uploads one or more files, each as a new source of the kind chosen for it (ADR 0009). */
export function AddSourceModal({ projectId, onClose, onAdded }: AddSourceModalProps) {
  const upload = useUploadSources(projectId);
  const { data: project } = useProject(projectId);
  const { data: current } = useSources(projectId);
  const showToast = useToast();
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  // One key per attempt whose outcome is unknown: kept across a retry after a network or
  // server failure, replaced once the API has given a definite answer or the files change.
  const idempotencyKey = useRef<string | null>(null);
  const formId = useId();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (files.length === 0) {
      setProblem('Choose a file to add.');
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    upload.mutate(
      { files, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (stored) => {
          idempotencyKey.current = null;
          if (stored.length > 0) {
            showToast(describeStored(stored, current));
          }
          onClose();
          onAdded?.(newlyAdded(stored, current));
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
            {upload.isPending
              ? 'Adding…'
              : files.length > 1
                ? `Add ${plural(files.length, 'source')}`
                : 'Add source'}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <SourceFilesPicker
          files={files}
          onChange={(chosen) => {
            setFiles(chosen);
            setProblem(null);
            idempotencyKey.current = null;
            upload.reset();
          }}
          limits={project?.limits.source}
          heldKinds={current?.map((version) => version.kind) ?? []}
          error={errorMessage}
          disabled={upload.isPending}
        />
        {upload.isPending && (
          <p role="status" className="text-[13px] text-muted">
            Adding {files.length > 1 ? 'the sources' : 'the source'}…
          </p>
        )}
      </form>
    </Modal>
  );
}
