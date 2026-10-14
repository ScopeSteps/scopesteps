import { versionLabel } from './types';
import type { BacklogVersion, ScopeStatus } from './types';
import { useBacklogVersion } from './useBacklogVersion';

interface VersionSelectProps {
  projectId: string;
  version: BacklogVersion;
  status: ScopeStatus;
  onSelect: (versionId: string) => void;
}

/**
 * Switches between the version in view, the project's draft in progress and its current
 * baseline. Older approved versions join this list once the API can list a project's versions.
 */
export function VersionSelect({ projectId, version, status, onSelect }: VersionSelectProps) {
  const { data: open } = useBacklogVersion(
    projectId,
    status.open_version_id === version.id ? null : status.open_version_id,
  );
  const { data: baseline } = useBacklogVersion(
    projectId,
    status.baseline_version_id === version.id ? null : status.baseline_version_id,
  );
  const options = [open, version, baseline].filter(
    (option, index, all): option is BacklogVersion =>
      option !== undefined && all.findIndex((other) => other?.id === option.id) === index,
  );

  if (options.length < 2) {
    return null;
  }
  return (
    <label className="flex items-center gap-2 text-[13px]">
      <span className="sr-only">Version</span>
      <select
        value={version.id}
        onChange={(event) => {
          onSelect(event.currentTarget.value);
        }}
        className="min-h-[34px] rounded-lg border border-line bg-surface px-2.5 text-fg focus:border-accent focus:shadow-focus focus:outline-none"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {versionLabel(option, status)}
          </option>
        ))}
      </select>
    </label>
  );
}
