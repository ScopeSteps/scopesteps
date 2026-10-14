import type { ButtonHTMLAttributes } from 'react';

import { cx } from '@/lib/cx';

type ButtonVariant = 'default' | 'primary' | 'soft' | 'ghost' | 'danger';
type ButtonSize = 'md' | 'sm';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  default: 'border-line bg-surface font-medium enabled:hover:bg-hover',
  primary:
    'border-accent bg-accent font-semibold text-accent-fg enabled:hover:border-accent-hover enabled:hover:bg-accent-hover',
  soft: 'border-accent-line bg-accent-soft font-semibold text-accent-ink enabled:hover:border-accent',
  ghost:
    'border-transparent bg-transparent font-medium text-muted enabled:hover:bg-hover enabled:hover:text-fg',
  danger: 'border-bad-line bg-surface font-medium text-bad-ink enabled:hover:bg-hover',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  md: 'min-h-9 rounded-lg px-3.5 text-sm',
  sm: 'min-h-[30px] rounded-md px-2.5 text-[13px]',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** A text button. Defaults to `type="button"`, so it never submits a form by accident. */
export function Button({
  variant = 'default',
  size = 'md',
  type = 'button',
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        'inline-flex cursor-pointer items-center justify-center gap-1.5 border whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-45',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
      {...props}
    />
  );
}
