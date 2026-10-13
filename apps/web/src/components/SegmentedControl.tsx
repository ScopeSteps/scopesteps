import { cx } from '@/lib/cx';

interface SegmentOption<Value extends string> {
  value: Value;
  label: string;
}

interface SegmentedControlProps<Value extends string> {
  /** Names the group for assistive technology: "Filter", "Format". */
  label: string;
  options: readonly SegmentOption<Value>[];
  value: Value;
  onChange: (value: Value) => void;
}

/** A small set of mutually exclusive views or filters, one of them always pressed. */
export function SegmentedControl<Value extends string>({
  label,
  options,
  value,
  onChange,
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
          onClick={() => {
            onChange(option.value);
          }}
          className={cx(
            'min-h-7 cursor-pointer rounded-md px-2.5 text-[13px] font-medium',
            option.value === value ? 'bg-surface text-fg shadow-raised' : 'text-muted',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
