import { Link } from 'react-router';

import { KIND_LABELS } from './types';
import type { SourceVersion } from './types';

interface SourceVersionListProps {
  versions: SourceVersion[];
  selectedVersionId: string | undefined;
}

export function SourceVersionList({ versions, selectedVersionId }: SourceVersionListProps) {
  return (
    <nav aria-label="Stored sources">
      <ul className="grid gap-3 sm:grid-cols-2">
        {versions.map((version) => {
          const isSelected = version.id === selectedVersionId;
          return (
            <li
              key={version.id}
              className={`rounded border p-3 ${isSelected ? 'border-accent bg-accent-soft' : 'border-line'}`}
            >
              <Link
                to={{ search: `?version=${version.id}` }}
                aria-current={isSelected ? 'true' : undefined}
                className="font-medium text-accent-ink underline focus-visible:outline-2 focus-visible:outline-accent"
              >
                {KIND_LABELS[version.kind]}: {version.filename}
              </Link>
              <p className="mt-1 text-sm text-muted">
                Version {version.version} · {version.block_count} paragraphs · {version.word_count}{' '}
                words
              </p>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 text-xs text-muted">
                <dt>Source ID</dt>
                <dd className="font-mono break-all">{version.source_id}</dd>
                <dt>Version ID</dt>
                <dd className="font-mono break-all">{version.id}</dd>
              </dl>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
