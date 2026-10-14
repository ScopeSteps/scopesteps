import { CitationChip } from '@/components/CitationChip';
import { SourceCitationChip, useBlockSource } from '@/features/sources';

import type { Run } from './types';

interface RunCitationChipProps {
  projectId: string;
  run: Run;
  /** The id the draft cites, such as B2 or A1. It is the model's handle, never shown. */
  label: string;
  /** The finding the citation backs, for the chip's accessible name. */
  about: string;
  onOpen: () => void;
}

/**
 * A finding's citation, named as the rest of the app names it: "Brief ¶2" for a source
 * paragraph, "Answer" for a reviewer's answer.
 */
export function RunCitationChip({ projectId, run, label, about, onOpen }: RunCitationChipProps) {
  const ref = run.block_refs.find((candidate) => candidate.label === label);
  if (ref?.source_block_id) {
    return (
      <SourceChip
        projectId={projectId}
        run={run}
        blockId={ref.source_block_id}
        about={about}
        onOpen={onOpen}
      />
    );
  }
  const name = ref?.question_id ? 'Answer' : 'Source';
  return (
    <CitationChip onClick={onOpen} aria-label={`${name}, evidence for: ${about}`}>
      {name}
    </CitationChip>
  );
}

function SourceChip({
  projectId,
  run,
  blockId,
  about,
  onOpen,
}: {
  projectId: string;
  run: Run;
  blockId: string;
  about: string;
  onOpen: () => void;
}) {
  const located = useBlockSource(projectId, run.source_version_ids, blockId);
  if (located.status === 'found') {
    return (
      <SourceCitationChip
        projectId={projectId}
        sourceVersionId={located.sourceVersionId}
        blockId={blockId}
        about={about}
        onOpen={onOpen}
      />
    );
  }
  return (
    <CitationChip onClick={onOpen} aria-label={`Source, evidence for: ${about}`}>
      Source
    </CitationChip>
  );
}
