import { useId } from 'react';

import { GRANTABLE_ROLES } from '@/features/identity';
import type { GrantableRole } from '@/features/identity';

interface RoleCheckboxesProps {
  value: readonly GrantableRole[];
  onChange: (roles: GrantableRole[]) => void;
  /** Shown under the choices and announced with them. */
  error?: string | null;
}

/** The roles a person can be given, each with what it allows. Roles combine. */
export function RoleCheckboxes({ value, onChange, error }: RoleCheckboxesProps) {
  const errorId = useId();
  return (
    <fieldset
      className="flex flex-col gap-2"
      aria-describedby={error ? errorId : undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="mb-1 text-[13px] font-semibold">Roles</legend>
      {GRANTABLE_ROLES.map(({ role, label, allows }) => (
        <label key={role} className="flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            className="mt-1 size-4 accent-accent"
            checked={value.includes(role)}
            onChange={(event) => {
              const checked = event.currentTarget.checked;
              onChange(
                GRANTABLE_ROLES.map((r) => r.role).filter((r) =>
                  r === role ? checked : value.includes(r),
                ),
              );
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
