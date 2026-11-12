interface MeterProps {
  /** Names what is measured, for assistive technology. */
  label: string;
  value: number;
  max: number;
  /** The figure as text, e.g. "9 of 10 (90%)"; the meter never carries it alone. */
  valueText: string;
}

/** A single ratio against its whole: an accent fill on a track of the same ramp. */
export function Meter({ label, value, max, valueText }: MeterProps) {
  const share = max <= 0 ? 1 : Math.min(1, Math.max(0, value / max));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={valueText}
      className="h-2 w-full overflow-hidden rounded-full bg-accent-soft"
    >
      <div className="h-full rounded-full bg-accent" style={{ width: `${String(share * 100)}%` }} />
    </div>
  );
}
