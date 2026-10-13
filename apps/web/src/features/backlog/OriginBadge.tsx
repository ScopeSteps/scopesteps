import { ORIGIN_LABELS } from './types';
import type { ClaimOrigin } from './types';

const STYLES: Record<ClaimOrigin, string> = {
  source: 'border-green-700 bg-green-50 text-green-900',
  human: 'border-blue-700 bg-blue-50 text-blue-900',
  proposed: 'border-amber-700 bg-amber-50 text-amber-900 border-dashed',
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
