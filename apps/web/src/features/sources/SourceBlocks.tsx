import { useEffect, useRef } from 'react';
import { Link } from 'react-router';

import { describeError } from '@/lib/apiError';

import { useSourceBlocks } from './useSourceBlocks';

interface SourceBlocksProps {
  projectId: string;
  sourceVersionId: string;
  selectedBlockId: string | null;
}

export function SourceBlocks({ projectId, sourceVersionId, selectedBlockId }: SourceBlocksProps) {
  const { data: blocks, error, isPending, refetch } = useSourceBlocks(projectId, sourceVersionId);
  const selectedBlock = useRef<HTMLLIElement>(null);

  // Bring a linked paragraph into view once it is rendered, as a URL fragment would.
  useEffect(() => {
    selectedBlock.current?.scrollIntoView({ block: 'center' });
    selectedBlock.current?.focus({ preventScroll: true });
  }, [selectedBlockId, blocks]);

  if (isPending) {
    return <p role="status">Loading paragraphs…</p>;
  }
  if (error) {
    return (
      <div role="alert" className="text-sm text-bad-ink">
        <p>Could not load the paragraphs. {describeError(error)}</p>
        <button type="button" onClick={() => void refetch()} className="mt-2 underline">
          Try again
        </button>
      </div>
    );
  }

  return (
    <ol className="space-y-3">
      {blocks.map((block) => {
        const isSelected = block.id === selectedBlockId;
        return (
          <li
            key={block.id}
            ref={isSelected ? selectedBlock : undefined}
            tabIndex={isSelected ? -1 : undefined}
            aria-current={isSelected ? 'true' : undefined}
            className={`rounded border-l-4 py-2 pr-2 pl-3 ${isSelected ? 'border-accent bg-accent-soft' : 'border-line'}`}
          >
            <p className="text-xs text-muted">
              <Link
                to={{ search: `?version=${sourceVersionId}&block=${block.id}` }}
                className="font-medium text-accent-ink underline focus-visible:outline-2 focus-visible:outline-accent"
              >
                Paragraph {block.ordinal}
              </Link>{' '}
              · Block ID <span className="font-mono break-all">{block.id}</span>
            </p>
            {/* Source text is data: rendered as a text node, so markup in it stays inert. */}
            <p className="mt-1 whitespace-pre-wrap">{block.text}</p>
          </li>
        );
      })}
    </ol>
  );
}
