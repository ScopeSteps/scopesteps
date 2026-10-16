import { useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { describeError } from '@/lib/apiError';

import { MAX_NAME, MAX_ROLE } from './people';
import type { Person } from './people';

interface PersonEditFormProps {
  person: Person;
  saving: boolean;
  /** The person on screen is out of date, so saving would be refused. */
  locked: boolean;
  /** A failed save, other than a stale person, which the card reports. */
  error: Error | null;
  onSave: (name: string, role: string) => void;
  onCancel: () => void;
}

/** Corrects the name and role the agent read, in place of the card. */
export function PersonEditForm({
  person,
  saving,
  locked,
  error,
  onSave,
  onCancel,
}: PersonEditFormProps) {
  const [name, setName] = useState(person.name);
  const [role, setRole] = useState(person.role);
  const [showProblems, setShowProblems] = useState(false);
  const nameProblem = name.trim() ? null : 'Enter a name.';
  const { extracted } = person;

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (nameProblem) {
      setShowProblems(true);
      return;
    }
    onSave(name.trim(), role.trim());
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      autoComplete="off"
      aria-label={`Edit ${person.name}`}
      className="flex flex-col gap-3"
    >
      <strong className="font-semibold">Edit person</strong>
      <TextField
        label="Name"
        value={name}
        onChange={setName}
        maxLength={MAX_NAME}
        disabled={saving}
        error={showProblems ? nameProblem : null}
        focusOnMount
      />
      <TextField
        label="Role"
        value={role}
        onChange={setRole}
        maxLength={MAX_ROLE}
        disabled={saving}
      />
      {person.correction && (
        <span className="text-xs text-subtle">
          {extracted ? 'Agent extracted' : 'Entered'}: {extracted?.name ?? person.entered_name}
          {extracted?.role ? `, ${extracted.role}` : ', no role'}. Saving those values removes the
          correction.
        </span>
      )}
      {error && (
        <Banner tone="bad" role="alert">
          The correction was not saved. {describeError(error)}
        </Banner>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" variant="primary" disabled={saving || locked}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
        <Button size="sm" disabled={saving} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
