import { Link } from 'react-router';

import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import { locateQuote } from './quote';
import { sourceViewerPath } from './sourceViewerPath';
import { KIND_LABELS } from './types';
import { useSourceBlocks } from './useSourceBlocks';
import { useSources } from './useSources';

interface SourcePassageProps {
  projectId: string;
  sourceVersionId: string;
  blockId: string;
  /** The words a claim quotes from the paragraph; omitted when it cites the whole paragraph. */
  quote?: string | null | undefined;
}

/** One cited paragraph, with the document version it comes from and the quoted words marked. */
export function SourcePassage({ projectId, sourceVersionId, blockId, quote }: SourcePassageProps) {
  const { data: blocks, error, isPending, refetch } = useSourceBlocks(projectId, sourceVersionId);
  const { data: versions } = useSources(projectId);

  if (isPending) {
    return (
      <p role="status" className="text-[13px] text-subtle">
        Loading the cited passage…
      </p>
    );
  }
  if (error) {
    return (
      <div role="alert" className="flex flex-col items-start gap-1.5 text-[13px] text-bad-ink">
        <p>Could not load the cited passage. {describeError(error)}</p>
        <Button size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  const block = blocks.find((candidate) => candidate.id === blockId);
  if (!block) {
    return (
      <p role="alert" className="text-[13px] text-bad-ink">
        This citation points at a paragraph that is not in the stored source version.
      </p>
    );
  }

  // The list holds current versions only; a superseded one is still citable.
  const version = versions?.find((candidate) => candidate.id === sourceVersionId);
  const parts = locateQuote(block.text, quote);

  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-xs text-subtle">
        {version
          ? `${version.filename} · ${KIND_LABELS[version.kind]} v${String(version.version)}`
          : 'Earlier source version'}{' '}
        · paragraph {block.ordinal}
      </figcaption>
      {quote && !parts && (
        <p className="text-[13px]">
          Quoted: <q>{quote}</q>
        </p>
      )}
      {/* Source text is data: rendered as text nodes, so markup in it stays inert. */}
      <blockquote className="m-0 rounded-[10px] border border-line bg-surface-2 px-3.5 py-3 text-[15px] leading-[1.55] whitespace-pre-wrap">
        {parts ? (
          <>
            {parts.before}
            <mark className="rounded-sm bg-accent-soft text-fg">{parts.quote}</mark>
            {parts.after}
          </>
        ) : (
          block.text
        )}
      </blockquote>
      <Link
        to={sourceViewerPath(projectId, sourceVersionId, block.id)}
        className="self-start text-[13px] font-medium text-accent-ink hover:underline"
      >
        Open full source
      </Link>
    </figure>
  );
}
