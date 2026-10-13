import type { ReactNode } from 'react';

import { cx } from '@/lib/cx';

/** Status tones carry meaning: warn needs a decision, bad is a failure or block, ok has passed. */
export type TagTone = 'accent' | 'neutral' | 'warn' | 'bad' | 'ok';

const TONE_CLASSES: Record<TagTone, string> = {
  accent: 'bg-accent-soft text-accent-ink',
  neutral: 'border border-line bg-surface-2 text-muted',
  warn: 'bg-warn-soft text-warn-ink',
  bad: 'bg-bad-soft text-bad-ink',
  ok: 'bg-ok-soft text-ok-ink',
};

interface TagProps {
  tone?: TagTone;
  children: ReactNode;
  className?: string;
}

export function Tag({ tone = 'neutral', children, className }: TagProps) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full px-[7px] py-0.5 text-[11px] leading-normal font-semibold whitespace-nowrap',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
