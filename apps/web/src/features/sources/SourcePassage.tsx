import { Link } from 'react-router';

import { describeError } from '@/lib/apiError';

import { locateQuote } from './quote';
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
    return <p role="status">Loading the cited passage…</p>;
  }
  if (error) {
    return (
      <div role="alert" className="text-sm text-bad-ink">
        <p>Could not load the cited passage. {describeError(error)}</p>
        <button type="button" onClick={() => void refetch()} className="mt-1 underline">
          Try again
        </button>
      </div>
    );
  }
  const block = blocks.find((candidate) => candidate.id === blockId);
  if (!block) {
    return (
      <p role="alert" className="text-sm text-bad-ink">
        This citation points at a paragraph that is not in the stored source version.
      </p>
    );
  }

  // The list holds current versions only; a superseded one is still citable.
  const version = versions?.find((candidate) => candidate.id === sourceVersionId);
  const parts = locateQuote(block.text, quote);

  return (
    <figure className="rounded border border-line p-3">
      <figcaption className="text-xs text-muted">
        <span className="font-medium">
          {version
            ? `${KIND_LABELS[version.kind]}: ${version.filename}, version ${String(version.version)}`
            : 'Earlier source version'}
        </span>{' '}
        · Paragraph {block.ordinal}
        <span className="mt-1 block font-mono break-all text-muted">
          Version {sourceVersionId} · Block {block.id}
        </span>
      </figcaption>
      {quote && !parts && (
        <p className="mt-2 text-sm">
          Quoted: <q>{quote}</q>
        </p>
      )}
      {/* Source text is data: rendered as text nodes, so markup in it stays inert. */}
      <blockquote className="mt-2 border-l-4 border-line pl-3 text-sm whitespace-pre-wrap">
        {parts ? (
          <>
            {parts.before}
            <mark className="bg-accent-soft text-fg">{parts.quote}</mark>
            {parts.after}
          </>
        ) : (
          block.text
        )}
      </blockquote>
      <Link
        to={`/projects/${projectId}/sources?version=${sourceVersionId}&block=${block.id}`}
        className="mt-2 inline-block text-xs text-accent-ink underline focus-visible:outline-2 focus-visible:outline-accent"
      >
        Open in Sources
      </Link>
    </figure>
  );
}
