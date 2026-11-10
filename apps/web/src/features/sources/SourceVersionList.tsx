import { Button } from '@/components/Button';
import { Tag } from '@/components/Tag';

import { formatAddedAt, plural } from './format';
import type { SourceVersion } from './types';

interface SourceVersionListProps {
  /** Newest first, as the API lists them. */
  versions: readonly SourceVersion[];
  /** The version the viewer shows now. */
  shownId: string;
  onOpen: (version: SourceVersion) => void;
}

/** A source's versions, newest first; each opens in the viewer, earlier ones read-only. */
export function SourceVersionList({ versions, shownId, onOpen }: SourceVersionListProps) {
  return (
    <section aria-labelledby="source-versions-heading" className="flex flex-col gap-1">
      <h3 id="source-versions-heading" className="text-xs font-semibold text-subtle">
        Versions
      </h3>
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {versions.map((version, index) => {
          const shown = version.id === shownId;
          return (
            <li key={version.id} className="flex flex-wrap items-center gap-2 text-[13px]">
              <Button
                size="sm"
                variant={shown ? 'soft' : 'ghost'}
                aria-current={shown ? 'true' : undefined}
                aria-label={`Open v${String(version.version)}: ${version.filename}`}
                onClick={() => {
                  onOpen(version);
                }}
              >
                <span className="font-mono tabular-nums">v{version.version}</span>
                <span className="[overflow-wrap:anywhere]">{version.filename}</span>
              </Button>
              {index === 0 && <Tag tone="ok">Current</Tag>}
              <span className="text-xs text-subtle">
                {plural(version.word_count, 'word')} · added{' '}
                <time dateTime={version.created_at}>{formatAddedAt(version.created_at)}</time>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
