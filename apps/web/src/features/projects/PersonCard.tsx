import { useEffect, useId, useRef, useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { SegmentedControl } from '@/components/SegmentedControl';
import { Tag } from '@/components/Tag';
import { useMemberName } from '@/features/identity';
import { SourceCitationChip } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import { isStalePerson, personEvidence, rightsSummary, statedRights } from './people';
import type { ConfirmableRights, Person } from './people';
import { PersonEditForm } from './PersonEditForm';
import { usePersonCommands } from './usePersonCommands';

const RIGHTS_OPTIONS = [
  { value: 'decides', label: 'Decides' },
  { value: 'advises', label: 'Advises' },
  { value: 'unknown', label: 'Unknown' },
] as const satisfies readonly { value: ConfirmableRights; label: string }[];

interface PersonCardProps {
  projectId: string;
  person: Person;
  canEdit: boolean;
  onShowEvidence: () => void;
  onReload: () => Promise<unknown>;
}

/** One person the sources name: who they are, their decision rights and where that comes from. */
export function PersonCard({
  projectId,
  person,
  canEdit,
  onShowEvidence,
  onReload,
}: PersonCardProps) {
  const [editing, setEditing] = useState(false);
  const commands = usePersonCommands(projectId, person);
  const memberName = useMemberName(projectId);
  const headingId = useId();
  const editButton = useRef<HTMLButtonElement>(null);
  // Set when the form closes, so focus goes back to the Edit button that opened it.
  const returnFocus = useRef(false);
  const stale = isStalePerson(commands.error) ? commands.error : null;
  const failed = stale ? null : commands.error;
  const rights = rightsSummary(person);
  const statedInSource = statedRights(person) !== 'not_stated';
  const { evidence, rightsEvidence } = personEvidence(person);

  useEffect(() => {
    if (!editing && returnFocus.current) {
      returnFocus.current = false;
      editButton.current?.focus();
    }
  }, [editing]);

  function closeForm() {
    returnFocus.current = true;
    setEditing(false);
  }

  async function reload() {
    commands.reset();
    if (editing) {
      closeForm();
    }
    await onReload();
  }

  const byWhom = (userId: string) => memberName(userId) ?? 'a team member';
  const history = [
    person.correction && `Corrected by ${byWhom(person.correction.corrected_by)}`,
    person.confirmed_rights &&
      `Rights confirmed by ${byWhom(person.confirmed_rights.confirmed_by)}`,
  ].filter(Boolean);

  const staleBanner = stale && (
    <Banner
      tone="bad"
      role="alert"
      action={
        <Button size="sm" onClick={() => void reload()}>
          Reload
        </Button>
      }
    >
      {stale.code === 'RIGHTS_STATED_IN_SOURCE'
        ? 'A source now states this person’s decision rights, so they are no longer confirmed by hand.'
        : 'Someone else changed this person after you opened the page.'}{' '}
      Your change was not saved. Reload to see the latest.
    </Banner>
  );

  if (editing) {
    return (
      <Card tone="focus" className="min-w-0">
        <PersonEditForm
          person={person}
          saving={commands.isPending}
          locked={stale !== null}
          error={commands.sentType === 'correct' ? failed : null}
          onSave={(name, role) => {
            commands.send({ type: 'correct', name, role }, closeForm);
          }}
          onCancel={() => {
            commands.reset();
            closeForm();
          }}
        />
        {staleBanner}
      </Card>
    );
  }

  return (
    <Card aria-labelledby={headingId} role="article" className="min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={headingId} className="font-semibold break-words">
            {person.name}
          </h3>
          <p className="text-[13px] break-words text-muted">{person.role || 'No role stated'}</p>
        </div>
        <Tag tone={rights.tone} className="flex-none">
          {rights.tag}
        </Tag>
      </div>
      {person.extracted?.said && <p className="text-[13px]">{person.extracted.said}</p>}
      <p className="flex flex-wrap items-center gap-1.5 text-[13px]">
        <span>{rights.text}</span>
        {evidence.map((reference) => (
          <SourceCitationChip
            key={`named-${reference.block_id}-${reference.quote ?? ''}`}
            projectId={projectId}
            sourceVersionId={reference.source_version_id}
            blockId={reference.block_id}
            about={person.name}
            onOpen={onShowEvidence}
          />
        ))}
        {rightsEvidence.map((reference) => (
          <SourceCitationChip
            key={`rights-${reference.block_id}-${reference.quote ?? ''}`}
            projectId={projectId}
            sourceVersionId={reference.source_version_id}
            blockId={reference.block_id}
            about={`${person.name}’s decision right`}
            onOpen={onShowEvidence}
          />
        ))}
      </p>
      {history.length > 0 && <p className="text-xs text-subtle">{history.join(' · ')}</p>}
      {canEdit && (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {!statedInSource && (
            <SegmentedControl
              label={`Decision rights for ${person.name}`}
              options={RIGHTS_OPTIONS}
              value={person.confirmed_rights?.rights ?? null}
              disabled={stale !== null}
              onChange={(value) => {
                if (value !== person.confirmed_rights?.rights) {
                  commands.send({ type: 'confirm', rights: value });
                }
              }}
            />
          )}
          {commands.isPending && commands.sentType === 'confirm' && (
            <span role="status" className="text-xs text-subtle">
              Saving…
            </span>
          )}
          <Button
            ref={editButton}
            size="sm"
            variant="ghost"
            className="ml-auto text-accent-ink"
            aria-label={`Edit ${person.name}`}
            onClick={() => {
              commands.reset();
              setEditing(true);
            }}
          >
            Edit
          </Button>
        </div>
      )}
      {failed && commands.sentType === 'confirm' && (
        <Banner tone="bad" role="alert">
          The decision rights were not saved. {describeError(failed)}
        </Banner>
      )}
      {staleBanner}
    </Card>
  );
}
