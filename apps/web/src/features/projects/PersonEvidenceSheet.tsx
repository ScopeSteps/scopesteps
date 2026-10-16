import { SideSheet } from '@/components/SideSheet';
import { SourcePassage } from '@/features/sources';

import { personEvidence } from './people';
import type { Person, PersonEvidence } from './people';

interface PersonEvidenceSheetProps {
  projectId: string;
  person: Person;
  onClose: () => void;
}

function Passages({ projectId, evidence }: { projectId: string; evidence: PersonEvidence[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0">
      {evidence.map((reference) => (
        <li key={`${reference.block_id}-${reference.quote ?? ''}`}>
          <SourcePassage
            projectId={projectId}
            sourceVersionId={reference.source_version_id}
            blockId={reference.block_id}
            quote={reference.quote}
          />
        </li>
      ))}
    </ul>
  );
}

/** Where the sources name a person and, if one does, where it states their decision right. */
export function PersonEvidenceSheet({ projectId, person, onClose }: PersonEvidenceSheetProps) {
  const { evidence, rightsEvidence } = personEvidence(person);

  return (
    <SideSheet title="Evidence" onClose={onClose}>
      <span className="text-xs text-subtle">Person named in the sources</span>
      <p className="font-medium">
        {person.name}
        {person.role && <span className="font-normal text-muted"> · {person.role}</span>}
      </p>
      {evidence.length > 0 && (
        <section aria-labelledby="person-named-heading" className="flex flex-col gap-2">
          <h3 id="person-named-heading" className="text-[13px] font-semibold">
            Where the sources name them
          </h3>
          <Passages projectId={projectId} evidence={evidence} />
        </section>
      )}
      {rightsEvidence.length > 0 && (
        <section aria-labelledby="person-rights-heading" className="flex flex-col gap-2">
          <h3 id="person-rights-heading" className="text-[13px] font-semibold">
            Where a source states their decision right
          </h3>
          <Passages projectId={projectId} evidence={rightsEvidence} />
        </section>
      )}
      <p className="text-xs text-subtle">
        A citation shows where a detail came from. Whether it’s interpreted correctly is your call.
      </p>
    </SideSheet>
  );
}
