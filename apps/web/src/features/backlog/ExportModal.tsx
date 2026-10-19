import { useQueryClient } from '@tanstack/react-query';
import { useId, useMemo, useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { Select } from '@/components/Select';
import { ApiError, describeError } from '@/lib/apiError';

import { CsvPreview } from './CsvPreview';
import { jiraRows, saveExport } from './exportFile';
import { versionName } from './types';
import { useApprovedVersions } from './useVersionHistory';
import { useBacklogExport } from './useBacklogExport';

const PLACEHOLDER = 'min-h-[240px] w-full rounded-lg border border-line bg-surface-2 p-2.5 text-xs';

interface ExportModalProps {
  projectId: string;
  /** The approved version the modal opens on; any other approved version can be chosen. */
  versionId: string;
  onClose: () => void;
}

/**
 * Previews an approved version's Jira CSV as a table read from the file the server sent, then
 * downloads that same file. Whether a version may be exported is the server's answer, shown as
 * it gives it.
 */
export function ExportModal({ projectId, versionId, onClose }: ExportModalProps) {
  const [chosenId, setChosenId] = useState(versionId);
  const selectId = useId();
  const queryClient = useQueryClient();
  const versions = useApprovedVersions(projectId);
  const exported = useBacklogExport(projectId, chosenId);
  const file = exported.data;
  const rows = useMemo(() => (file ? jiraRows(file.text) : null), [file]);
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
      <div role="status" className={`${PLACEHOLDER} text-subtle`}>
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
  } else if (rows === null) {
    body = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void exported.refetch()}>
            Try again
          </Button>
        }
      >
        The server sent a file that is not the expected CSV, so it cannot be previewed or
        downloaded.
      </Banner>
    );
  } else {
    body = <CsvPreview rows={rows} />;
  }

  const downloadable = file?.filename && rows ? { ...file, filename: file.filename } : null;

  return (
    <Modal
      title={title}
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          <Button
            variant="primary"
            disabled={!downloadable}
            onClick={() => {
              if (downloadable) {
                saveExport(downloadable, downloadable.filename);
              }
            }}
          >
            Download CSV for Jira
          </Button>
        </>
      }
    >
      {picker}
      <p className="text-xs text-subtle">
        For Jira&rsquo;s CSV importer: one row per epic or story, and Issue ID and Parent keep each
        story under its epic.
        {file?.filename && (
          <>
            {' '}
            Downloads as <span className="font-mono">{file.filename}</span>.
          </>
        )}
      </p>
      {body}
    </Modal>
  );
}
