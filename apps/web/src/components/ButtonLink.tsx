import { Link } from 'react-router';
import type { LinkProps } from 'react-router';

import { buttonClasses } from './buttonClasses';
import type { ButtonSize, ButtonVariant } from './buttonClasses';

interface ButtonLinkProps extends Omit<LinkProps, 'className'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** Navigation that looks like a button, such as "Open backlog" in the chat. */
export function ButtonLink({ variant = 'default', size = 'md', ...props }: ButtonLinkProps) {
  return <Link className={buttonClasses(variant, size)} {...props} />;
}
