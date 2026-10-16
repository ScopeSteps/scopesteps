import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { useCanEdit } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { PersonCard } from './PersonCard';
import { PersonEvidenceSheet } from './PersonEvidenceSheet';
import { UnconfirmedSpeakers } from './UnconfirmedSpeakers';
import { usePeople } from './usePeople';

/** The People page: everyone the sources name, with their roles and decision rights. */
export function PeopleView({ projectId }: { projectId: string }) {
  const { data: people, error, isPending, refetch } = usePeople(projectId);
  const canEdit = useCanEdit(projectId);
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);

  if (isPending) {
    return <p role="status">Loading people…</p>;
  }
  if (error) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the people in this project. {describeError(error)}
      </Banner>
    );
  }
  if (people.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <UnconfirmedSpeakers projectId={projectId} />
        <EmptyState title="No people yet">
          After the agent’s first run, everyone named in your sources appears here with their role
          and any decision rights the sources state. Speakers you confirm in a transcript’s
          Who&apos;s who appear here too.
        </EmptyState>
      </div>
    );
  }

  const shown = people.find((person) => person.id === evidenceFor);

  return (
    <section aria-labelledby="people-heading" className="flex flex-col gap-4">
      <h2 id="people-heading" className="sr-only">
        People on this project
      </h2>
      <UnconfirmedSpeakers projectId={projectId} />
      <p className="text-muted">
        {canEdit
          ? 'People named in your sources and speakers you confirmed. Fix any name or role the agent got wrong. Decision rights appear only when a source states them; confirm the rest yourself.'
          : 'People named in your sources and confirmed speakers, with their role and any decision rights the sources state.'}
      </p>
      <ul
        aria-label="People"
        className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(min(300px,100%),1fr))] gap-3 p-0"
      >
        {people.map((person) => (
          <li key={person.id} className="flex min-w-0 flex-col">
            <PersonCard
              projectId={projectId}
              person={person}
              canEdit={canEdit}
              onShowEvidence={() => {
                setEvidenceFor(person.id);
              }}
              onReload={refetch}
            />
          </li>
        ))}
      </ul>
      {shown && (
        <PersonEvidenceSheet
          projectId={projectId}
          person={shown}
          onClose={() => {
            setEvidenceFor(null);
          }}
        />
      )}
    </section>
  );
}
