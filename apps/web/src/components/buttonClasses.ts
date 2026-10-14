import { cx } from '@/lib/cx';

export type ButtonVariant = 'default' | 'primary' | 'soft' | 'ghost' | 'danger';
export type ButtonSize = 'md' | 'sm';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  default: 'border-line bg-surface font-medium not-disabled:hover:bg-hover',
  primary:
    'border-accent bg-accent font-semibold text-accent-fg not-disabled:hover:border-accent-hover not-disabled:hover:bg-accent-hover',
  soft: 'border-accent-line bg-accent-soft font-semibold text-accent-ink not-disabled:hover:border-accent',
  ghost:
    'border-transparent bg-transparent font-medium text-muted not-disabled:hover:bg-hover not-disabled:hover:text-fg',
  danger: 'border-bad-line bg-surface font-medium text-bad-ink not-disabled:hover:bg-hover',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  md: 'min-h-9 rounded-lg px-3.5 text-sm',
  sm: 'min-h-[30px] rounded-md px-2.5 text-[13px]',
};

/** The look of a button, for a link that acts as one (`ButtonLink`). */
export function buttonClasses(
  variant: ButtonVariant = 'default',
  size: ButtonSize = 'md',
  className?: string,
): string {
  return cx(
    'inline-flex cursor-pointer items-center justify-center gap-1.5 border whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-45',
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    className,
  );
}
