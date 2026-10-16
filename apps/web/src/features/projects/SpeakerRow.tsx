import { useId } from 'react';

import { Select } from '@/components/Select';
import { Tag } from '@/components/Tag';
import { TextField } from '@/components/TextField';

import type { Person } from './people';
import { MEETING_ROLE_SUGGESTIONS, personPick, STATUS_TAGS } from './speakers';
import type { Pick, Speaker, SpeakerDraft, SpeakerField } from './speakers';

// The API's limits on a participant's name and meeting role (SpeakerMappingRequest).
const MAX_NAME = 80;
const MAX_MEETING_ROLE = 80;

interface SpeakerRowProps {
  speaker: Speaker;
  draft: SpeakerDraft;
  people: readonly Person[];
  /** Null when the reader may only look. */
  onChange: ((draft: SpeakerDraft) => void) | null;
  disabled: boolean;
  /** What the server refused about this speaker's answer, shown next to that field. */
  refused: { field: SpeakerField; message: string } | null;
}

function pickLabel(pick: Pick, people: readonly Person[]): string {
  switch (pick) {
    case '':
      return 'Not confirmed yet';
    case 'new':
      return 'New participant';
    case 'not_a_person':
      return 'Not a person';
    default:
      return people.find((person) => personPick(person.id) === pick)?.name ?? 'A participant';
  }
}

function isPick(value: string): value is Pick {
  return value === '' || value === 'new' || value === 'not_a_person' || value.startsWith('person:');
}

/** One speaker label: who it is and their meeting role, editable unless `onChange` is null. */
export function SpeakerRow({
  speaker,
  draft,
  people,
  onChange,
  disabled,
  refused,
}: SpeakerRowProps) {
  const headingId = useId();
  const pickId = useId();
  const pickErrorId = useId();
  const status = STATUS_TAGS[speaker.status];
  const hasParticipant = draft.pick === 'new' || draft.pick.startsWith('person:');
  const turns = `${String(speaker.turn_count)} ${speaker.turn_count === 1 ? 'turn' : 'turns'}`;

  return (
    <li
      aria-labelledby={headingId}
      className="flex flex-col gap-2.5 border-t border-line px-1 py-3.5 first:border-t-0"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="text-sm font-semibold [overflow-wrap:anywhere]">
          {speaker.label}
        </h3>
        <span className="font-mono text-xs text-subtle tabular-nums">{turns}</span>
        <Tag tone={status.tone} className="ml-auto">
          {status.label}
        </Tag>
      </div>
      {speaker.sample && (
        <p className="text-[13px] text-muted [overflow-wrap:anywhere]">
          <span className="sr-only">First said: </span>“{speaker.sample}”
        </p>
      )}
      {onChange === null ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
          <dt className="text-subtle">Participant</dt>
          <dd>{pickLabel(draft.pick, people)}</dd>
          {hasParticipant && (
            <>
              <dt className="text-subtle">Meeting role</dt>
              <dd>{draft.meetingRole || 'Not given'}</dd>
            </>
          )}
        </dl>
      ) : (
        <div className="grid grid-cols-2 gap-3 max-wide:grid-cols-1">
          <div className="flex flex-col gap-[5px]">
            <label htmlFor={pickId} className="text-[13px] font-semibold">
              Who is {speaker.label}?
            </label>
            <Select
              id={pickId}
              value={draft.pick}
              disabled={disabled}
              aria-invalid={refused?.field === 'pick' ? true : undefined}
              aria-describedby={refused?.field === 'pick' ? pickErrorId : undefined}
              className="min-h-[38px] text-sm"
              onChange={(event) => {
                const pick = event.currentTarget.value;
                if (isPick(pick)) {
                  const person = people.find((p) => personPick(p.id) === pick);
                  onChange({
                    ...draft,
                    pick,
                    meetingRole: person ? (person.meeting_role?.value ?? '') : draft.meetingRole,
                  });
                }
              }}
            >
              <option value="">Not confirmed yet</option>
              {people.length > 0 && (
                <optgroup label="Participants">
                  {people.map((person) => (
                    <option key={person.id} value={personPick(person.id)}>
                      {person.name}
                    </option>
                  ))}
                </optgroup>
              )}
              <option value="new">New participant…</option>
              <option value="not_a_person">Not a person</option>
            </Select>
            {refused?.field === 'pick' && (
              <span id={pickErrorId} className="text-[13px] text-bad-ink">
                {refused.message}
              </span>
            )}
          </div>
          {hasParticipant && (
            <TextField
              label={`Meeting role of ${speaker.label}`}
              value={draft.meetingRole}
              onChange={(meetingRole) => {
                onChange({ ...draft, meetingRole });
              }}
              suggestions={MEETING_ROLE_SUGGESTIONS}
              maxLength={MAX_MEETING_ROLE}
              disabled={disabled}
              help="Pick one or type your own."
              error={refused?.field === 'meeting_role' ? refused.message : null}
            />
          )}
          {draft.pick === 'new' && (
            <TextField
              label={`Name of the new participant for ${speaker.label}`}
              value={draft.name}
              onChange={(name) => {
                onChange({ ...draft, name });
              }}
              maxLength={MAX_NAME}
              disabled={disabled}
              error={refused?.field === 'name' ? refused.message : null}
            />
          )}
        </div>
      )}
    </li>
  );
}
