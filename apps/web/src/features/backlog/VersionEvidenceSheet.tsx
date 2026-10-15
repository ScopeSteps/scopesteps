import { SideSheet } from '@/components/SideSheet';

import { EvidenceSheet } from './EvidenceSheet';
import type { ClaimRef } from './types';
import { useBacklogVersion } from './useBacklogVersion';

interface VersionEvidenceSheetProps {
  projectId: string;
  versionId: string;
  claim: ClaimRef;
  onClose: () => void;
}

/** The evidence sheet for a claim of a version that the page around it has not loaded. */
export function VersionEvidenceSheet({
  projectId,
  versionId,
  claim,
  onClose,
}: VersionEvidenceSheetProps) {
  const { data: version, isPending } = useBacklogVersion(projectId, versionId);
  if (version) {
    return <EvidenceSheet version={version} claim={claim} onClose={onClose} />;
  }
  return (
    <SideSheet title="Evidence" onClose={onClose}>
      {isPending ? (
        <p role="status" className="text-[13px] text-subtle">
          Loading the evidence…
        </p>
      ) : (
        <p role="alert" className="text-[13px] text-bad-ink">
          The backlog version this evidence belongs to could not be loaded.
        </p>
      )}
    </SideSheet>
  );
}
