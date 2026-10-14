import { useId } from 'react';

import { Button } from '@/components/Button';
import { Select } from '@/components/Select';

import { asOption, versionLabel } from './types';
import type { BacklogVersion, ScopeStatus } from './types';
import { useVersionHistory } from './useVersionHistory';

interface VersionSelectProps {
  projectId: string;
  version: BacklogVersion;
  status: ScopeStatus | undefined;
  onSelect: (versionId: string) => void;
}

/**
 * Switches between every version in the project's history, newest first. Hidden when the
 * history holds nothing but the version in view; when it cannot be read, offers the version in
 * view and a retry.
 */
export function VersionSelect({ projectId, version, status, onSelect }: VersionSelectProps) {
  const errorId = useId();
  const history = useVersionHistory(projectId);
  const listed = history.data ?? [];
  const options = listed.some((option) => option.id === version.id)
    ? listed
    : [asOption(version, status), ...listed];

  // While the history loads, nothing appears, so a project with one version never shows it.
  if (history.isPending || (history.isSuccess && options.length < 2)) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        aria-label="Version"
        aria-describedby={history.error ? errorId : undefined}
        value={version.id}
        onChange={(event) => {
          onSelect(event.currentTarget.value);
        }}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {versionLabel(option, status)}
          </option>
        ))}
      </Select>
      {history.error && (
        <>
          <span id={errorId} role="alert" className="text-xs text-bad-ink">
            Could not list the versions.
          </span>
          <Button size="sm" onClick={() => void history.refetch()}>
            Try again
          </Button>
        </>
      )}
    </div>
  );
}
