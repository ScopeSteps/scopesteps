import type { ComponentProps } from 'react';

import { cx } from '@/lib/cx';

/** The app's native select. Give it a label: a `<label>`, `aria-label` or `aria-labelledby`. */
export function Select({ className, ...props }: ComponentProps<'select'>) {
  return (
    <select
      className={cx(
        'min-h-[34px] max-w-full rounded-lg border border-line bg-surface px-2.5 text-[13px] text-fg focus:border-accent focus:shadow-focus focus:outline-none disabled:bg-surface-2 disabled:text-muted',
        className,
      )}
      {...props}
    />
  );
}
