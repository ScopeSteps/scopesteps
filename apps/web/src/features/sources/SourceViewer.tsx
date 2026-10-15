import { useEffect, useRef } from 'react';
import { Link } from 'react-router';

import { Button } from '@/components/Button';
import { SideSheet } from '@/components/SideSheet';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { formatAddedAt, plural } from './format';
import { RemoveSource } from './RemoveSource';
import { KIND_LABELS, sourceLabel } from './types';
import type { SourceVersion } from './types';
import { useSourceBlocks } from './useSourceBlocks';

interface SourceViewerProps {
  projectId: string;
  sourceVersionId: string;
  /** The version's details, when it is one of the current versions the list returned. */
  version: SourceVersion | undefined;
  /** False while the list of current versions is still loading. */
  versionsLoaded: boolean;
  selectedBlockId: string | null;
  /** Offers removal of a current source; the API still decides whether it may go. */
  canRemove: boolean;
  onClose: () => void;
}

/** One source version, paragraph by paragraph, as the API split and numbered it. */
export function SourceViewer({
  projectId,
  sourceVersionId,
  version,
  versionsLoaded,
  selectedBlockId,
  canRemove,
  onClose,
}: SourceViewerProps) {
  const { data: blocks, error, isPending, refetch } = useSourceBlocks(projectId, sourceVersionId);
  const selectedBlock = useRef<HTMLLIElement>(null);

  // Bring a linked paragraph into view once it is rendered, as a URL fragment would.
  useEffect(() => {
    selectedBlock.current?.scrollIntoView({ block: 'center' });
    selectedBlock.current?.focus({ preventScroll: true });
  }, [selectedBlockId, blocks]);

  return (
    <SideSheet
      title={
        version ? (
          <>
            <span className="font-mono tabular-nums">{sourceLabel(version.source_number)}</span>{' '}
            {version.filename}
          </>
        ) : (
          'Earlier source version'
        )
      }
      onClose={onClose}
      footer={
        version &&
        canRemove && (
          <RemoveSource
            key={version.source_id}
            projectId={projectId}
            version={version}
            onRemoved={onClose}
          />
        )
      }
    >
      {version ? (
        <p className="text-xs text-subtle">
          {KIND_LABELS[version.kind]} · v{version.version} · {plural(version.word_count, 'word')} ·
          added {formatAddedAt(version.created_at)}
        </p>
      ) : (
        versionsLoaded && (
          <p className="text-xs text-subtle">
            Version <span className="font-mono break-all">{sourceVersionId}</span> is not the
            current version of a source.
          </p>
        )
      )}
      {isPending && (
        <p role="status" className="text-[13px] text-subtle">
          Loading paragraphs…
        </p>
      )}
      {error && (
        <div role="alert" className="flex flex-col items-start gap-1.5 text-[13px] text-bad-ink">
          <p>Could not load the paragraphs. {describeError(error)}</p>
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
      )}
      {blocks && (
        <ol aria-label="Paragraphs" className="m-0 flex list-none flex-col gap-0.5 p-0">
          {blocks.map((block) => {
            const isSelected = block.id === selectedBlockId;
            return (
              <li
                key={block.id}
                ref={isSelected ? selectedBlock : undefined}
                tabIndex={isSelected ? -1 : undefined}
                aria-current={isSelected ? 'true' : undefined}
                className={cx(
                  'grid grid-cols-[36px_minmax(0,1fr)] gap-2 rounded-lg p-2',
                  isSelected && 'bg-accent-soft',
                )}
              >
                <Link
                  to={{ search: `?version=${sourceVersionId}&block=${block.id}` }}
                  replace
                  aria-label={`Paragraph ${String(block.ordinal)}`}
                  className="font-mono text-xs text-subtle tabular-nums hover:text-accent-ink hover:underline"
                >
                  ¶{block.ordinal}
                </Link>
                {/* Source text is data: rendered as a text node, so markup in it stays inert. */}
                <span className="whitespace-pre-wrap">{block.text}</span>
              </li>
            );
          })}
        </ol>
      )}
    </SideSheet>
  );
}
