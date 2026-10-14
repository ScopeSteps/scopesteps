import { ORIGIN_LABELS } from './types';
import type { ClaimOrigin } from './types';

const STYLES: Record<ClaimOrigin, string> = {
  source: 'border-ok-ink bg-ok-soft text-ok-ink',
  human: 'border-accent bg-accent-soft text-accent-ink',
  proposed: 'border-warn-line bg-warn-soft text-warn-ink border-dashed',
  person: 'border-line-strong bg-surface text-fg',
};

/** Says in words where a claim comes from; the colour only repeats it. */
export function OriginBadge({ origin }: { origin: ClaimOrigin }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-xs font-medium ${STYLES[origin]}`}
    >
      {ORIGIN_LABELS[origin]}
    </span>
  );
}
