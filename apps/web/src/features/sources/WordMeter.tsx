import { formatBytes } from './format';
import type { SourceLimits } from './types';

interface WordMeterProps {
  words: number;
  /** The server's limits; without them only the count is shown. */
  limits: SourceLimits | undefined;
}

export function WordMeter({ words, limits }: WordMeterProps) {
  if (!limits) {
    return <span className="text-xs text-subtle">{words.toLocaleString()} words stored</span>;
  }
  const percent = Math.min(100, (words / limits.max_words) * 100);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div
        role="img"
        aria-label={`${words.toLocaleString()} of ${limits.max_words.toLocaleString()} words used`}
        className="h-1.5 w-40 overflow-hidden rounded-[3px] bg-line"
      >
        {/* Computed: the bar fills to the share of the limit in use. */}
        <div className="h-full bg-accent" style={{ width: `${percent.toFixed(1)}%` }} />
      </div>
      <span className="text-xs text-subtle">
        {words.toLocaleString()} / {limits.max_words.toLocaleString()} words · TXT or Markdown, up
        to {formatBytes(limits.max_bytes)} each
      </span>
    </div>
  );
}
