import { cx } from '@/lib/cx';

export type DiffKind = 'added' | 'changed' | 'removed';

const DIFFS: Record<DiffKind, { sign: string; label: string; classes: string }> = {
  added: { sign: '+', label: 'Added', classes: 'bg-accent text-accent-fg' },
  changed: {
    sign: '~',
    label: 'Changed',
    classes: 'border border-warn-line bg-warn-soft text-warn-ink',
  },
  removed: {
    sign: '−',
    label: 'Removed',
    classes: 'border border-line-strong bg-surface-2 text-fg',
  },
};

/**
 * Marks what a change does to an entry, as the prototype's diff tags do. `label` words a
 * conditional change ("Removed if reversed") in the same style.
 */
export function DiffTag({ kind, label }: { kind: DiffKind; label?: string }) {
  const { sign, classes } = DIFFS[kind];
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full px-[7px] py-0.5 text-[11px] leading-normal font-bold whitespace-nowrap',
        classes,
      )}
    >
      <span aria-hidden="true">{sign}</span>
      {label ?? DIFFS[kind].label}
    </span>
  );
}
