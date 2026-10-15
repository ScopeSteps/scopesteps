import { useCallback, useId, useRef } from 'react';
import type { HTMLAttributes, ReactNode } from 'react';

import { cx } from '@/lib/cx';

interface TextFieldProps {
  label: ReactNode;
  value: string;
  /** Leave out for a read-only field. */
  onChange?: (value: string) => void;
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
  /** The input's type. Ignored for a textarea. */
  type?: 'text' | 'email' | 'password';
  autoComplete?: string;
  inputMode?: HTMLAttributes<HTMLInputElement>['inputMode'];
  placeholder?: string;
  readOnly?: boolean;
  /** Marks the control invalid when its message is shown elsewhere, e.g. a form's own alert. */
  invalid?: boolean;
  /** The id of that message, so the control is described by it. */
  describedBy?: string | undefined;
  /** A control inside the input's right edge, such as a show-password toggle. */
  trailing?: ReactNode;
  /** The control's name in its form, e.g. to find and focus it. */
  name?: string;
}

const CONTROL =
  'min-h-[38px] w-full rounded-lg border bg-surface px-2.5 py-2 text-sm text-fg focus:border-accent focus:shadow-focus focus:outline-none disabled:bg-surface-2 disabled:text-muted read-only:bg-surface-2 read-only:text-muted';

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
  type = 'text',
  autoComplete,
  inputMode,
  placeholder,
  readOnly,
  invalid = false,
  describedBy: externalDescription,
  trailing,
  name,
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
  const describedBy = [help ? helpId : null, error ? errorId : null, externalDescription ?? null]
    .filter(Boolean)
    .join(' ');
  const isInvalid = Boolean(error) || invalid;
  const shared = {
    id,
    name,
    value,
    maxLength,
    disabled,
    readOnly,
    'aria-invalid': isInvalid ? true : undefined,
    'aria-describedby': describedBy || undefined,
  };
  const controlClass = cx(CONTROL, isInvalid ? 'border-bad-line' : 'border-line');

  return (
    <div className="flex flex-col gap-[5px]">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}
      </label>
      {rows === undefined ? (
        <div className="relative">
          <input
            type={type}
            ref={focusRef}
            autoComplete={autoComplete}
            inputMode={inputMode}
            placeholder={placeholder}
            {...shared}
            className={cx(controlClass, trailing !== undefined && 'pr-16')}
            onChange={(event) => {
              onChange?.(event.currentTarget.value);
            }}
          />
          {trailing !== undefined && (
            <span className="absolute top-1/2 right-1.5 -translate-y-1/2">{trailing}</span>
          )}
        </div>
      ) : (
        <textarea
          rows={rows}
          ref={focusRef}
          {...shared}
          className={cx(controlClass, 'resize-y leading-normal')}
          onChange={(event) => {
            onChange?.(event.currentTarget.value);
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
