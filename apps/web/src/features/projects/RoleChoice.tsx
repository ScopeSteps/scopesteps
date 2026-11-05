import { useId } from 'react';

import { GRANTABLE_ROLES } from '@/features/identity';
import type { GrantableRole } from '@/features/identity';

interface RoleChoiceProps {
  value: GrantableRole;
  onChange: (role: GrantableRole) => void;
  /** Shown under the choices and announced with them. */
  error?: string | null;
}

/** One role per person, each with what it allows; each includes the ones above it in the list. */
export function RoleChoice({ value, onChange, error }: RoleChoiceProps) {
  const name = useId();
  const errorId = useId();
  return (
    <fieldset
      className="flex flex-col gap-2"
      aria-describedby={error ? errorId : undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="mb-1 text-[13px] font-semibold">Role</legend>
      {GRANTABLE_ROLES.map(({ role, label, allows }) => (
        <label key={role} className="flex cursor-pointer items-start gap-2.5">
          <input
            type="radio"
            name={name}
            value={role}
            className="mt-1 size-4 accent-accent"
            checked={value === role}
            onChange={() => {
              onChange(role);
            }}
          />
          <span className="flex flex-col leading-tight">
            <span className="font-medium">{label}</span>
            <span className="text-xs text-subtle">{allows}</span>
          </span>
        </label>
      ))}
      {error && (
        <p id={errorId} className="text-[13px] text-bad-ink">
          {error}
        </p>
      )}
    </fieldset>
  );
}
