import { cx } from '@/lib/cx';

/** `warn` marks something that needs a decision; its label says what, so colour is not alone. */
export type BadgeTone = 'accent' | 'warn';

const TONE_CLASSES: Record<BadgeTone, string> = {
  accent: 'bg-accent text-accent-fg',
  warn: 'border border-warn-line bg-warn-soft text-warn-ink',
};

interface BadgeProps {
  count: number;
  /** Read out in place of the bare number: "3 need attention". */
  label: string;
  tone?: BadgeTone | undefined;
}

/** A count on a navigation item. Renders nothing for zero. */
export function Badge({ count, label, tone = 'accent' }: BadgeProps) {
  if (count <= 0) {
    return null;
  }
  return (
    <span
      title={label}
      className={cx(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-[5px] text-[11px] font-bold',
        TONE_CLASSES[tone],
      )}
    >
      <span aria-hidden="true">{count}</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
