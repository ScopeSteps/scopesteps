import type { ButtonHTMLAttributes, Ref } from 'react';

import { cx } from '@/lib/cx';

import { Icon } from './Icon';
import type { IconName } from './Icon';

interface IconButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'aria-label' | 'children' | 'title'
> {
  icon: IconName;
  /** The accessible name, also shown as the tooltip. */
  label: string;
  ref?: Ref<HTMLButtonElement>;
}

export function IconButton({ icon, label, type = 'button', className, ...props }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex size-9 flex-none cursor-pointer items-center justify-center rounded-lg text-muted hover:bg-hover hover:text-fg',
        className,
      )}
      {...props}
    >
      <Icon name={icon} />
    </button>
  );
}
