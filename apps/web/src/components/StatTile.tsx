import type { ReactNode } from 'react';
import { Link } from 'react-router';

interface StatTileProps {
  label: string;
  /** The figure, in mono with tabular numbers. */
  value: ReactNode;
  /** One line under the figure, e.g. what it is counted from. */
  detail?: ReactNode;
  /** The page with the details behind the figure; the whole tile links there. */
  to: string;
  /** Extra content under the detail, such as a meter. */
  children?: ReactNode;
}

/** One headline figure that opens the page it comes from. */
export function StatTile({ label, value, detail, to, children }: StatTileProps) {
  return (
    <Link
      to={to}
      className="flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-surface px-4 py-3.5 text-fg no-underline hover:border-line-strong hover:bg-hover focus-visible:shadow-focus focus-visible:outline-none"
    >
      {/* The spaces keep the parts apart in the link's accessible name; flex layout hides them. */}
      <span className="text-xs text-subtle">{label}</span>{' '}
      <span className="font-mono text-2xl font-semibold tabular-nums">{value}</span>{' '}
      {detail && <span className="text-xs text-muted">{detail}</span>}
      {children}
    </Link>
  );
}
