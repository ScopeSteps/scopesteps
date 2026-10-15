import type { ButtonHTMLAttributes, Ref } from 'react';

import { buttonClasses } from './buttonClasses';
import type { ButtonSize, ButtonVariant } from './buttonClasses';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  ref?: Ref<HTMLButtonElement>;
}

/** A text button. Defaults to `type="button"`, so it never submits a form by accident. */
export function Button({
  variant = 'default',
  size = 'md',
  type = 'button',
  className,
  ...props
}: ButtonProps) {
  return <button type={type} className={buttonClasses(variant, size, className)} {...props} />;
}
