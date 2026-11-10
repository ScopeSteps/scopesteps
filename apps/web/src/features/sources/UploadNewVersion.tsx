import { useId, useRef, useState } from 'react';

import { Button } from '@/components/Button';
import { useToast } from '@/components/toastContext';
import { ApiError } from '@/lib/apiError';

import { ACCEPTED_SOURCE_FILES, checkSourceFile } from './checkSourceFile';
import { sourceLabel } from './types';
import type { SourceLimits, SourceVersion } from './types';
import { uploadRefusal } from './uploadRefusal';
import { useAddSourceVersion } from './useSourceVersions';

interface UploadNewVersionProps {
  projectId: string;
  /** The source's current version, which the file replaces as the newest. */
  version: SourceVersion;
  limits: SourceLimits | undefined;
  /** After a new version is stored: the viewer moves to it. */
  onUploaded: (version: SourceVersion) => void;
}

function fileSignature(file: File): string {
  return `${file.name}:${String(file.size)}:${String(file.lastModified)}`;
}

/**
 * Stores a corrected file as the source's next version. Earlier versions stay as they were, so
 * what cites them still opens. The same file as now changes nothing, and the API says so.
 */
export function UploadNewVersion({
  projectId,
  version,
  limits,
  onUploaded,
}: UploadNewVersionProps) {
  const add = useAddSourceVersion(projectId);
  const showToast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const pendingKey = useRef<{ signature: string; key: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [unchanged, setUnchanged] = useState(false);
  const messageId = useId();
  const label = sourceLabel(version.source_number);
  const refusal = uploadRefusal(problem ?? add.error);

  function upload(file: File) {
    setUnchanged(false);
    add.reset();
    const local = checkSourceFile(file, limits);
    setProblem(local);
    if (local) {
      return;
    }
    const signature = fileSignature(file);
    if (pendingKey.current?.signature !== signature) {
      pendingKey.current = { signature, key: crypto.randomUUID() };
    }
    const key = pendingKey.current.key;
    // Handled from the promise, not the call's callbacks: once v2 is stored the list reloads,
    // the version shown is no longer current and this control unmounts, which drops them.
    add.mutateAsync({ sourceId: version.source_id, file, idempotencyKey: key }).then(
      (stored) => {
        pendingKey.current = null;
        if (stored.id === version.id) {
          setUnchanged(true);
          return;
        }
        showToast(`Saved as v${String(stored.version)} of ${label}.`);
        onUploaded(stored);
      },
      (failure: unknown) => {
        if (failure instanceof ApiError && !failure.retryable) {
          pendingKey.current = null;
        }
      },
    );
  }

  return (
    <div className="mr-auto flex flex-col items-start gap-1.5">
      <input
        ref={input}
        type="file"
        accept={ACCEPTED_SOURCE_FILES}
        className="sr-only"
        tabIndex={-1}
        aria-label={`File for the new version of ${label}`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Cleared, so choosing the same file again after a fix still uploads it.
          event.target.value = '';
          if (file) {
            upload(file);
          }
        }}
      />
      <Button
        disabled={add.isPending}
        aria-describedby={refusal || unchanged ? messageId : undefined}
        onClick={() => {
          input.current?.click();
        }}
      >
        {add.isPending ? 'Uploading…' : 'Upload new version'}
      </Button>
      {refusal && (
        <p id={messageId} role="alert" className="text-[13px] text-bad-ink">
          The new version was not saved. {refusal.message}
        </p>
      )}
      {unchanged && (
        <p id={messageId} role="status" className="text-[13px] text-muted">
          That file is the same as v{version.version}, so nothing changed.
        </p>
      )}
    </div>
  );
}
