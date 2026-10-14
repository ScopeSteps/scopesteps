import { useId } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Select } from '@/components/Select';
import { describeError } from '@/lib/apiError';

import { ChangeRow } from './ChangeRow';
import { versionName } from './types';
import type { VersionSummary } from './types';
import { useBacklogVersion } from './useBacklogVersion';
import { useVersionComparison } from './useVersionComparison';
import { useApprovedVersions } from './useVersionHistory';

function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${String(count)} ${count === 1 ? noun : many}`;
}

/**
 * Compares any two approved versions, kept in the URL as `from` and `to`. The list of changes is
 * the server's comparison by stable ids; the page only lays it out.
 */
export function VersionCompare({ projectId }: { projectId: string }) {
  const headingId = useId();
  const [searchParams, setSearchParams] = useSearchParams();
  const approved = useApprovedVersions(projectId);
  const versions = approved.data ?? [];
  const pick = (param: string, fallback: VersionSummary | undefined) =>
    versions.find((version) => version.id === searchParams.get(param)) ?? fallback;
  const from = versions.length < 2 ? undefined : pick('from', versions[1]);
  const to = versions.length < 2 ? undefined : pick('to', versions[0]);

  function choose(param: 'from' | 'to', id: string) {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(param, id);
        return next;
      },
      { replace: true },
    );
  }

  let body;
  if (approved.isPending) {
    body = (
      <p role="status" className="text-subtle">
        Loading approved versions…
      </p>
    );
  } else if (approved.error) {
    body = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void approved.refetch()}>
            Try again
          </Button>
        }
      >
        Could not list the approved versions. {describeError(approved.error)}
      </Banner>
    );
  } else if (!from || !to) {
    body = (
      <p className="text-subtle">
        {versions[0]
          ? `Only ${versionName(versions[0].number)} is approved so far. Compare needs two approved versions.`
          : 'Nothing to compare yet. Approved versions appear here once a baseline is approved.'}
      </p>
    );
  } else if (from.id === to.id) {
    body = (
      <p role="status" className="text-subtle">
        Pick two different versions.
      </p>
    );
  } else {
    body = <ComparisonResult projectId={projectId} from={from} to={to} />;
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={headingId} className="text-base font-semibold">
          Compare approved versions
        </h2>
        {from && to && (
          <div className="flex flex-wrap items-center gap-2">
            <VersionPicker
              label="From version"
              versions={versions}
              value={from.id}
              onChange={(id) => {
                choose('from', id);
              }}
            />
            <span className="text-xs text-subtle">to</span>
            <VersionPicker
              label="To version"
              versions={versions}
              value={to.id}
              onChange={(id) => {
                choose('to', id);
              }}
            />
          </div>
        )}
      </div>
      {body}
    </section>
  );
}

interface VersionPickerProps {
  label: string;
  versions: VersionSummary[];
  value: string;
  onChange: (id: string) => void;
}

function VersionPicker({ label, versions, value, onChange }: VersionPickerProps) {
  return (
    <Select
      aria-label={label}
      value={value}
      onChange={(event) => {
        onChange(event.currentTarget.value);
      }}
    >
      {versions.map((version) => (
        <option key={version.id} value={version.id}>
          {versionName(version.number)}
        </option>
      ))}
    </Select>
  );
}

interface ComparisonResultProps {
  projectId: string;
  from: VersionSummary;
  to: VersionSummary;
}

function ComparisonResult({ projectId, from, to }: ComparisonResultProps) {
  const comparison = useVersionComparison(projectId, from.id, to.id);
  // The stories the comparison reports nothing for are the unchanged ones.
  const { data: target } = useBacklogVersion(projectId, to.id);
  const fromName = versionName(from.number);
  const toName = versionName(to.number);

  if (comparison.isPending) {
    return (
      <p role="status" className="text-subtle">
        Comparing {fromName} with {toName}…
      </p>
    );
  }
  if (comparison.error) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void comparison.refetch()}>
            Try again
          </Button>
        }
      >
        Could not compare {fromName} with {toName}. {describeError(comparison.error)}
      </Banner>
    );
  }

  const { operations } = comparison.data;
  const changedIds = new Set(operations.map((operation) => operation.item_id));
  const unchanged = target?.items.filter(
    (item) => item.kind === 'story' && !changedIds.has(item.id),
  ).length;

  return (
    <div className="flex flex-col gap-2">
      {operations.length === 0 ? (
        <p className="text-subtle">No differences.</p>
      ) : (
        <ul aria-label={`Changes from ${fromName} to ${toName}`} className="flex flex-col gap-1.5">
          {operations.map((operation) => (
            <ChangeRow key={operation.item_id} change={operation} />
          ))}
        </ul>
      )}
      {unchanged !== undefined && (
        <p className="text-xs text-subtle">
          {plural(unchanged, 'story', 'stories')} unchanged between {fromName} and {toName}.
        </p>
      )}
    </div>
  );
}
