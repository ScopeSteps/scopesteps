import { useCallback, useId, useRef } from 'react';
import type { ReactNode } from 'react';

import { cx } from '@/lib/cx';

interface TextFieldProps {
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  /** A textarea of this many rows instead of a one-line input. */
  rows?: number;
  maxLength?: number;
  disabled?: boolean;
  /** A short hint under the control. */
  help?: ReactNode;
  /** Shown under the control and announced with it; marks the control invalid. */
  error?: string | null;
  /** Moves focus into the control when it first renders, e.g. a field the user just added. */
  focusOnMount?: boolean;
}

const CONTROL =
  'min-h-[38px] w-full rounded-lg border bg-surface px-2.5 py-2 text-sm text-fg focus:border-accent focus:shadow-focus focus:outline-none disabled:bg-surface-2 disabled:text-muted';

/** A labelled text input, or a textarea when `rows` is set. */
export function TextField({
  label,
  value,
  onChange,
  rows,
  maxLength,
  disabled = false,
  help,
  error,
  focusOnMount = false,
}: TextFieldProps) {
  const id = useId();
  // Read once: the control takes focus when it mounts, never on a later render.
  const focusWhenMounted = useRef(focusOnMount);
  const focusRef = useCallback((node: HTMLElement | null) => {
    if (node && focusWhenMounted.current) {
      node.focus();
    }
  }, []);
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const describedBy = [help ? helpId : null, error ? errorId : null].filter(Boolean).join(' ');
  const shared = {
    id,
    value,
    maxLength,
    disabled,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy || undefined,
  };
  const controlClass = cx(CONTROL, error ? 'border-bad-line' : 'border-line');

  return (
    <div className="flex flex-col gap-[5px]">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}
      </label>
      {rows === undefined ? (
        <input
          type="text"
          ref={focusRef}
          {...shared}
          className={controlClass}
          onChange={(event) => {
            onChange(event.currentTarget.value);
          }}
        />
      ) : (
        <textarea
          rows={rows}
          ref={focusRef}
          {...shared}
          className={cx(controlClass, 'resize-y leading-normal')}
          onChange={(event) => {
            onChange(event.currentTarget.value);
          }}
        />
      )}
      {help && (
        <span id={helpId} className="text-xs text-subtle">
          {help}
        </span>
      )}
      {error && (
        <span id={errorId} className="text-[13px] text-bad-ink">
          {error}
        </span>
      )}
    </div>
  );
}
