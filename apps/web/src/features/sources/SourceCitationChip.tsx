import { CitationChip } from '@/components/CitationChip';

import { KIND_SHORT_LABELS } from './types';
import { useSourceBlocks } from './useSourceBlocks';
import { useSources } from './useSources';

interface SourceCitationChipProps {
  projectId: string;
  sourceVersionId: string;
  blockId: string;
  /** The claim the paragraph backs, added to the accessible name after the visible label. */
  about?: string;
  onOpen: () => void;
}

/**
 * Names a cited paragraph by its source and the paragraph number the API gave it, "Brief ¶2",
 * and opens its evidence. Until the paragraphs load it shows the source alone.
 */
export function SourceCitationChip({
  projectId,
  sourceVersionId,
  blockId,
  about,
  onOpen,
}: SourceCitationChipProps) {
  const { data: versions } = useSources(projectId);
  const { data: blocks } = useSourceBlocks(projectId, sourceVersionId);
  const version = versions?.find((candidate) => candidate.id === sourceVersionId);
  const ordinal = blocks?.find((block) => block.id === blockId)?.ordinal;
  const source = version ? KIND_SHORT_LABELS[version.kind] : 'Source';

  const label = ordinal === undefined ? source : `${source} ¶${String(ordinal)}`;

  return (
    <CitationChip
      onClick={onOpen}
      aria-label={about ? `${label}, evidence for: ${about}` : undefined}
    >
      {label}
    </CitationChip>
  );
}
