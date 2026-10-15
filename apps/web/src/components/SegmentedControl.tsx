import { cx } from '@/lib/cx';

interface SegmentOption<Value extends string> {
  value: Value;
  label: string;
}

interface SegmentedControlProps<Value extends string> {
  /** Names the group for assistive technology: "Filter", "Format". */
  label: string;
  options: readonly SegmentOption<Value>[];
  /** The pressed option, or null when none is chosen yet. */
  value: Value | null;
  onChange: (value: Value) => void;
  disabled?: boolean;
}

/** A small set of mutually exclusive options: a view, a filter or a choice not yet made. */
export function SegmentedControl<Value extends string>({
  label,
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedControlProps<Value>) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex gap-0.5 self-start rounded-lg border border-line bg-surface-2 p-[3px]"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          disabled={disabled}
          onClick={() => {
            onChange(option.value);
          }}
          className={cx(
            'min-h-7 cursor-pointer rounded-md px-2.5 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-45',
            option.value === value ? 'bg-surface text-fg shadow-raised' : 'text-muted',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
