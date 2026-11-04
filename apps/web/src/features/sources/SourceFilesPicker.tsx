import { useId, useState } from 'react';
import type { DragEvent } from 'react';

import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';
import { Select } from '@/components/Select';
import { cx } from '@/lib/cx';

import { ACCEPTED_SOURCE_FILES, ACCEPTED_TYPES_TEXT, checkSourceFile } from './checkSourceFile';
import { formatBytes } from './format';
import { KIND_LABELS, SOURCE_KINDS } from './types';
import type { SourceFile, SourceKind, SourceLimits } from './types';
import { uploadRefusal } from './uploadRefusal';

interface SourceFilesPickerProps {
  files: readonly SourceFile[];
  onChange: (files: SourceFile[]) => void;
  /** The server's limits, for the hint and the browser's size check. */
  limits: SourceLimits | undefined;
  /**
   * The API's answer to the last upload of these files: shown next to the file it names, or
   * under the picker when it concerns the whole upload.
   */
  error?: Error | string | null;
  disabled?: boolean;
  /** Kinds the project already holds, so the suggestions carry on from them. */
  heldKinds?: readonly SourceKind[];
  /** Shown while no file is chosen, e.g. that sources can also be added later. */
  emptyHint?: string;
}

/**
 * A project usually starts from a brief and a transcript, so the first file missing one is
 * suggested as it; anything after is a supporting document. A WebVTT file only ever holds
 * captions, so it is suggested as a transcript. Each suggestion can be changed.
 */
function nextKind(
  heldKinds: readonly SourceKind[],
  files: readonly SourceFile[],
  file: File,
): SourceKind {
  if (file.name.toLowerCase().endsWith('.vtt')) {
    return 'transcript';
  }
  const held = new Set([...heldKinds, ...files.map((entry) => entry.kind)]);
  if (!held.has('brief')) {
    return 'brief';
  }
  return held.has('transcript') ? 'supporting_document' : 'transcript';
}

/**
 * Chooses one or more files, each with its kind, to upload together: in Add a source and in
 * step 2 of New project. It uploads nothing: pass the files to `useUploadSources`, which stores
 * all of them or none.
 */
export function SourceFilesPicker({
  files,
  onChange,
  limits,
  error = null,
  disabled = false,
  heldKinds = [],
  emptyHint = 'No files chosen yet.',
}: SourceFilesPickerProps) {
  const [refusals, setRefusals] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const rowErrorId = useId();
  const refusal = uploadRefusal(error);
  const refusedRow = refusal?.filename
    ? files.findIndex((entry) => entry.file.name === refusal.filename)
    : -1;
  const problems = refusal && refusedRow === -1 ? [...refusals, refusal.message] : refusals;

  function addFiles(chosen: readonly File[]) {
    const accepted = [...files];
    const refused: string[] = [];
    for (const file of chosen) {
      const refusal = checkSourceFile(file, limits);
      if (refusal) {
        refused.push(refusal);
      } else {
        accepted.push({ kind: nextKind(heldKinds, accepted, file), file });
      }
    }
    setRefusals(refused);
    onChange(accepted);
  }

  function dropFiles(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) {
      addFiles(Array.from(event.dataTransfer.files));
    }
  }

  function setKind(index: number, kind: SourceKind) {
    onChange(files.map((entry, at) => (at === index ? { ...entry, kind } : entry)));
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Dropping files is a shortcut for the file input, which stays the way to choose them by
          keyboard. */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(!disabled);
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={dropFiles}
        className={cx(
          'flex flex-col items-start gap-2 rounded-xl border border-dashed border-line-strong p-[18px]',
          dragging && 'border-accent-line bg-accent-soft',
        )}
      >
        <label htmlFor={inputId} className="text-[13px] font-semibold">
          Upload {ACCEPTED_TYPES_TEXT} files
        </label>
        <input
          id={inputId}
          type="file"
          multiple
          accept={ACCEPTED_SOURCE_FILES}
          disabled={disabled}
          aria-invalid={problems.length > 0}
          aria-describedby={problems.length > 0 ? `${hintId} ${errorId}` : hintId}
          onChange={(event) => {
            addFiles(Array.from(event.currentTarget.files ?? []));
            // Lets the same file be chosen again after it is taken off the list.
            event.currentTarget.value = '';
          }}
          className="w-full rounded-lg border border-line bg-surface p-2 text-[13px] file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-hover file:px-3 file:py-1 file:text-fg"
        />
        <span id={hintId} className="text-xs text-subtle">
          {limits
            ? `Up to ${formatBytes(limits.max_bytes)} per text file, ${formatBytes(limits.max_document_bytes)} per Word, PDF or .vtt file, and ${limits.max_words.toLocaleString()} words across all sources. `
            : 'Text, Markdown, Word, PDF or .vtt transcripts. '}
          You can also drop files here. Paragraphs are numbered so the agent can cite them. Scanned
          PDFs have no text to read.
        </span>
        {problems.length > 0 && (
          <div id={errorId} role="alert" className="flex flex-col gap-1 text-[13px] text-bad-ink">
            {problems.map((problem, index) => (
              <p key={index}>{problem}</p>
            ))}
          </div>
        )}
      </div>
      {files.length === 0 ? (
        <p className="text-xs text-subtle">{emptyHint}</p>
      ) : (
        <ul aria-label="Files to add" className="m-0 flex list-none flex-col gap-1.5 p-0">
          {files.map((entry, index) => (
            <li
              key={`${entry.file.name}-${String(entry.file.lastModified)}-${String(index)}`}
              className={cx(
                'flex flex-wrap items-center gap-2.5 rounded-[10px] border bg-surface px-3 py-2',
                index === refusedRow ? 'border-bad-line' : 'border-line',
              )}
            >
              <Icon name="sources" size={16} />
              <span className="min-w-40 flex-1 [overflow-wrap:anywhere]">
                {entry.file.name}{' '}
                <span className="text-xs text-subtle">· {formatBytes(entry.file.size)}</span>
              </span>
              <Select
                aria-label={`Type of ${entry.file.name}`}
                aria-invalid={index === refusedRow || undefined}
                aria-describedby={index === refusedRow ? rowErrorId : undefined}
                value={entry.kind}
                disabled={disabled}
                onChange={(event) => {
                  const kind = SOURCE_KINDS.find((option) => option === event.currentTarget.value);
                  if (kind) {
                    setKind(index, kind);
                  }
                }}
              >
                {SOURCE_KINDS.map((option) => (
                  <option key={option} value={option}>
                    {KIND_LABELS[option]}
                  </option>
                ))}
              </Select>
              <IconButton
                icon="close"
                label={`Remove ${entry.file.name}`}
                disabled={disabled}
                onClick={() => {
                  onChange(files.filter((_, at) => at !== index));
                }}
              />
              {index === refusedRow && refusal && (
                <p id={rowErrorId} role="alert" className="m-0 basis-full text-[13px] text-bad-ink">
                  {refusal.message}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
