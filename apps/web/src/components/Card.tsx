import type { ComponentPropsWithRef } from 'react';

import { cx } from '@/lib/cx';

/** `focus` marks the card the user is acting on; `decide` marks one that needs a decision. */
type CardTone = 'default' | 'focus' | 'decide';

const TONE_CLASSES: Record<CardTone, string> = {
  default: 'border-line bg-surface',
  focus: 'border-accent bg-surface shadow-focus',
  decide: 'border-warn-line bg-warn-soft',
};

interface CardProps extends ComponentPropsWithRef<'div'> {
  tone?: CardTone;
}

export function Card({ tone = 'default', className, ...props }: CardProps) {
  return (
    <div
      className={cx(
        'flex flex-col gap-2 rounded-xl border px-4 py-3.5 text-sm',
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    />
  );
}
