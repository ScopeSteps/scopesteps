import { useId } from 'react';

import { cx } from '@/lib/cx';

import { describeCount, describeImpact, IMPACT_KINDS, touches } from './impact';
import type { ChangeImpact, ScopeCount } from './impact';

type Part = 'unchanged' | 'changed' | 'removed' | 'added';

const PARTS: Record<Part, { label: string; fill: string }> = {
  unchanged: { label: 'Unchanged', fill: 'bg-chart-unchanged' },
  changed: { label: 'Changed', fill: 'bg-chart-changed' },
  removed: { label: 'Removed', fill: 'bg-chart-removed' },
  added: { label: 'Added', fill: 'bg-chart-added' },
};

// Before is what stays, changes or goes; after is what stays, changes or arrives. Both start
// with the work that stays, so the bars line up where the scope is the same.
const BEFORE: Part[] = ['unchanged', 'changed', 'removed'];
const AFTER: Part[] = ['unchanged', 'changed', 'added'];

function Bar({
  label,
  parts,
  scope,
  total,
  max,
}: {
  label: string;
  parts: Part[];
  scope: ScopeCount;
  total: number;
  max: number;
}) {
  const shown = parts.filter((part) => scope[part] > 0);
  return (
    <div className="grid grid-cols-[3rem_1fr_2rem] items-center gap-2">
      <span className="text-xs text-subtle">{label}</span>
      <div className="h-3 rounded-r bg-surface-2">
        <div
          className="flex h-full gap-0.5"
          style={{ width: max === 0 ? '0%' : `${String((total / max) * 100)}%` }}
        >
          {shown.map((part, index) => (
            <div
              key={part}
              title={`${String(scope[part])} ${PARTS[part].label.toLowerCase()}`}
              className={cx(
                'h-full min-w-0.5 basis-0',
                PARTS[part].fill,
                index === shown.length - 1 && 'rounded-r',
              )}
              style={{ flexGrow: scope[part] }}
            />
          ))}
        </div>
      </div>
      <span className="text-right font-mono text-xs tabular-nums">{total}</span>
    </div>
  );
}

/**
 * What a change does to the scope: a plain-language summary, a before-and-after chart and the
 * same figures as text. Every figure is the server's, counted from the two versions.
 */
export function ImpactPanel({ impact, name }: { impact: ChangeImpact; name: string }) {
  const figuresId = useId();
  const kinds = IMPACT_KINDS.filter(({ key }) => impact[key].before + impact[key].after > 0);
  const changes = IMPACT_KINDS.some(({ key }) => touches(impact[key]));
  return (
    <section
      // Named after its request: a page may show several.
      aria-label={`Impact of ${name} on scope`}
      className="flex flex-col gap-2.5 rounded-lg border border-line bg-surface p-3"
    >
      <h3 className="text-[13px] font-semibold">Impact on scope</h3>
      <p className="text-[13px]">{describeImpact(impact)}</p>
      {changes && (
        <>
          <ul
            aria-label="Chart legend"
            className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted"
          >
            {(Object.keys(PARTS) as Part[]).map((part) => (
              <li key={part} className="flex items-center gap-1.5">
                <span aria-hidden="true" className={cx('size-2.5 rounded-sm', PARTS[part].fill)} />
                {PARTS[part].label}
              </li>
            ))}
          </ul>
          <div
            role="img"
            aria-label={`Scope before and after ${name}`}
            aria-describedby={figuresId}
            className="flex flex-col gap-3"
          >
            {kinds.map(({ key, label }) => {
              const scope = impact[key];
              const max = Math.max(scope.before, scope.after);
              return (
                <div key={key} className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted">{label}</span>
                  <Bar label="Before" parts={BEFORE} scope={scope} total={scope.before} max={max} />
                  <Bar label="After" parts={AFTER} scope={scope} total={scope.after} max={max} />
                </div>
              );
            })}
          </div>
          <ul id={figuresId} className="flex flex-col gap-0.5 text-xs text-muted">
            {kinds.map(({ key, label }) => (
              <li key={key}>
                <span className="font-semibold">{label}:</span> {describeCount(impact[key])}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
