import { useEffect, useRef } from 'react';
import { Link } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { SideSheet } from '@/components/SideSheet';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { formatAddedAt, plural } from './format';
import { blockLocation } from './location';
import { RemoveSource } from './RemoveSource';
import { KIND_LABELS, sourceLabel } from './types';
import type { SourceLimits, SourceVersion } from './types';
import { UploadNewVersion } from './UploadNewVersion';
import { useSourceBlocks } from './useSourceBlocks';
import { useSourceVersions } from './useSourceVersions';
import { SourceVersionList } from './SourceVersionList';

interface SourceViewerProps {
  projectId: string;
  sourceVersionId: string;
  /** The version's details, when it is one of the current versions the list returned. */
  version: SourceVersion | undefined;
  /** False while the list of current versions is still loading. */
  versionsLoaded: boolean;
  selectedBlockId: string | null;
  /**
   * The source an earlier version belongs to, from the link that opened it; a current version
   * names its own. Without it an earlier version is shown with no details.
   */
  sourceId: string | null;
  /** Offers a new version and removal of a current source; the API still decides. */
  canEdit: boolean;
  limits: SourceLimits | undefined;
  /** Opens another version of the source, e.g. the one just uploaded. */
  onOpenVersion: (version: SourceVersion) => void;
  onClose: () => void;
}

/** One source version, paragraph by paragraph, as the API split and numbered it. */
export function SourceViewer({
  projectId,
  sourceVersionId,
  version: current,
  versionsLoaded,
  selectedBlockId,
  sourceId,
  canEdit,
  limits,
  onOpenVersion,
  onClose,
}: SourceViewerProps) {
  const { data: blocks, error, isPending, refetch } = useSourceBlocks(projectId, sourceVersionId);
  const history = useSourceVersions(projectId, current?.source_id ?? sourceId);
  const versions = history.data;
  // A current version comes from the sources list; an earlier one from its source's history.
  const version = current ?? versions?.find((each) => each.id === sourceVersionId);
  const newest = versions?.[0];
  const isEarlier = current === undefined && version !== undefined;
  const knownSourceId = version?.source_id ?? sourceId;
  const paragraphSearch = (blockId: string) =>
    knownSourceId
      ? `?version=${sourceVersionId}&source=${knownSourceId}&block=${blockId}`
      : `?version=${sourceVersionId}&block=${blockId}`;
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
        current &&
        canEdit && (
          <>
            <UploadNewVersion
              key={`upload-${current.id}`}
              projectId={projectId}
              version={current}
              limits={limits}
              onUploaded={onOpenVersion}
            />
            <RemoveSource
              key={current.source_id}
              projectId={projectId}
              version={current}
              onRemoved={onClose}
            />
          </>
        )
      }
    >
      {version ? (
        <p className="text-xs text-subtle">
          {KIND_LABELS[version.kind]} · v{version.version} · {plural(version.word_count, 'word')} ·
          added {formatAddedAt(version.created_at)}
        </p>
      ) : (
        versionsLoaded &&
        !history.isLoading && (
          <p className="text-xs text-subtle">
            Version <span className="font-mono break-all">{sourceVersionId}</span> is not the
            current version of a source.
          </p>
        )
      )}
      {isEarlier && (
        <Banner role="status">
          This is v{version.version}, an earlier version. It is kept as it was, so what cites it
          still opens, and it can’t be changed.
          {newest && newest.id !== version.id && (
            <>
              {' '}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  onOpenVersion(newest);
                }}
              >
                Open the current version, v{newest.version}
              </Button>
            </>
          )}
        </Banner>
      )}
      {versions && versions.length > 1 && (
        <SourceVersionList versions={versions} shownId={sourceVersionId} onOpen={onOpenVersion} />
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
          {blocks.map((block, index) => {
            const isSelected = block.id === selectedBlockId;
            // A page is named where it starts; a transcript's time is on every turn.
            const location =
              block.page !== null && block.page === blocks[index - 1]?.page
                ? null
                : blockLocation(block);
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
                  to={{ search: paragraphSearch(block.id) }}
                  replace
                  aria-label={`Paragraph ${String(block.ordinal)}`}
                  className="font-mono text-xs text-subtle tabular-nums hover:text-accent-ink hover:underline"
                >
                  ¶{block.ordinal}
                </Link>
                <span>
                  {location && (
                    <span className="block font-mono text-xs text-subtle tabular-nums">
                      {location}
                    </span>
                  )}
                  {/* Source text is data: rendered as a text node, so markup in it stays inert. */}
                  <span className="whitespace-pre-wrap">{block.text}</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </SideSheet>
  );
}
