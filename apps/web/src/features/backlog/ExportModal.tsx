import { useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { SegmentedControl } from '@/components/SegmentedControl';
import { Select } from '@/components/Select';
import { useToast } from '@/components/toastContext';
import { ApiError, describeError } from '@/lib/apiError';

import { saveExport } from './exportFile';
import type { ExportFormat } from './exportFile';
import { versionName } from './types';
import { useApprovedVersions } from './useVersionHistory';
import { useBacklogExport } from './useBacklogExport';

const FORMATS = [
  { value: 'json', label: 'JSON' },
  { value: 'markdown', label: 'Markdown' },
] as const;

const PREVIEW = 'min-h-[240px] w-full rounded-lg border border-line bg-surface-2 p-2.5 text-xs';

interface ExportModalProps {
  projectId: string;
  /** The approved version the modal opens on; any other approved version can be chosen. */
  versionId: string;
  onClose: () => void;
}

/**
 * Previews an approved version as the server exports it, then copies or downloads exactly that
 * text. Whether a version may be exported is the server's answer, shown as it gives it.
 */
export function ExportModal({ projectId, versionId, onClose }: ExportModalProps) {
  const [chosenId, setChosenId] = useState(versionId);
  const [format, setFormat] = useState<ExportFormat>('json');
  // The text the browser would not copy, so it was selected for the reader to copy by hand.
  const [selectedByHand, setSelectedByHand] = useState<string | null>(null);
  const preview = useRef<HTMLTextAreaElement>(null);
  const selectId = useId();
  const helpId = useId();
  const queryClient = useQueryClient();
  const showToast = useToast();
  const versions = useApprovedVersions(projectId);
  const exported = useBacklogExport(projectId, chosenId, format);
  const file = exported.data;
  const chosen = versions.data?.find((version) => version.id === chosenId);
  const title = chosen ? `Export ${versionName(chosen.number)}` : 'Export';

  if (versions.data?.length === 0) {
    return (
      <Modal
        title="Export"
        onClose={onClose}
        footer={
          <Button variant="primary" onClick={onClose}>
            OK
          </Button>
        }
      >
        <p>Only approved versions can be exported. Approve a baseline first.</p>
      </Modal>
    );
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setSelectedByHand(null);
      showToast('Copied to clipboard.');
    } catch {
      preview.current?.focus();
      preview.current?.select();
      setSelectedByHand(text);
    }
  }

  async function reload() {
    await queryClient.invalidateQueries({ queryKey: ['backlog', projectId] });
  }

  let picker;
  if (versions.error) {
    picker = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void versions.refetch()}>
            Try again
          </Button>
        }
      >
        Could not list the approved versions. {describeError(versions.error)}
      </Banner>
    );
  } else {
    picker = (
      <div className="flex items-center gap-2">
        <label htmlFor={selectId} className="text-xs text-subtle">
          Version
        </label>
        <Select
          id={selectId}
          value={chosenId}
          disabled={versions.isPending}
          onChange={(event) => {
            setChosenId(event.currentTarget.value);
          }}
        >
          {!chosen && (
            <option value={chosenId}>{versions.isPending ? 'Loading…' : 'This version'}</option>
          )}
          {versions.data?.map((version) => (
            <option key={version.id} value={version.id}>
              {versionName(version.number)}
            </option>
          ))}
        </Select>
      </div>
    );
  }

  let body;
  if (exported.isPending) {
    body = (
      <div role="status" className={`${PREVIEW} text-subtle`}>
        Loading the export…
      </div>
    );
  } else if (exported.error) {
    const error = exported.error;
    const definite = error instanceof ApiError && !error.retryable;
    body = (
      <Banner
        tone="bad"
        role="alert"
        action={
          error instanceof ApiError && error.status === 409 ? (
            <Button size="sm" onClick={() => void reload()}>
              Reload
            </Button>
          ) : definite ? undefined : (
            <Button size="sm" onClick={() => void exported.refetch()}>
              Try again
            </Button>
          )
        }
      >
        Could not export this version. {describeError(error)}
      </Banner>
    );
  } else {
    body = (
      <>
        <label htmlFor={`${selectId}-preview`} className="sr-only">
          Export content
        </label>
        <textarea
          id={`${selectId}-preview`}
          ref={preview}
          readOnly
          value={exported.data.text}
          aria-describedby={helpId}
          className={`${PREVIEW} resize-y font-mono text-fg focus:border-accent focus:shadow-focus focus:outline-none`}
        />
      </>
    );
  }

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          <Button
            disabled={!file?.filename}
            onClick={() => {
              if (file?.filename) {
                saveExport(file, file.filename);
              }
            }}
          >
            Download
          </Button>
          <Button
            variant="primary"
            disabled={!file}
            onClick={() => {
              if (file) {
                void copy(file.text);
              }
            }}
          >
            Copy
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        {picker}
        <SegmentedControl
          label="Format"
          options={FORMATS}
          value={format}
          onChange={(next) => {
            setFormat(next);
          }}
        />
      </div>
      {body}
      <span id={helpId} className="text-xs text-subtle">
        Includes evidence IDs, labeled suggestions and the approval hash.
        {file?.filename && (
          <>
            {' '}
            Downloads as <span className="font-mono">{file.filename}</span>.
          </>
        )}
      </span>
      {selectedByHand !== null && selectedByHand === file?.text && (
        <p role="status" className="text-[13px]">
          The browser blocked copying, so the text is selected. Press Ctrl+C or ⌘C to copy it.
        </p>
      )}
    </Modal>
  );
}
