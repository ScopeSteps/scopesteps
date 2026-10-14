import type { ReactNode } from 'react';

import { cx } from '@/lib/cx';

import { Icon } from './Icon';
import type { IconName } from './Icon';

type BannerTone = 'info' | 'warn' | 'bad';

const TONES: Record<BannerTone, { classes: string; icon: IconName }> = {
  info: { classes: 'border border-line bg-surface text-muted', icon: 'info' },
  warn: { classes: 'bg-warn-soft text-warn-ink', icon: 'warn' },
  bad: { classes: 'border border-bad-line bg-bad-soft text-bad-ink', icon: 'warn' },
};

interface BannerProps {
  tone?: BannerTone;
  /** `alert` for a failure the user must see now, `status` for a calm update. */
  role?: 'alert' | 'status';
  children: ReactNode;
  /** A button or link that acts on the message. */
  action?: ReactNode;
}

export function Banner({ tone = 'info', role, children, action }: BannerProps) {
  return (
    <div
      role={role}
      className={cx(
        'flex flex-wrap items-center gap-2.5 rounded-[10px] px-3.5 py-2.5 text-[13px]',
        TONES[tone].classes,
      )}
    >
      <span className="mt-0.5 flex-none self-start">
        <Icon name={TONES[tone].icon} size={16} />
      </span>
      <span className="min-w-0 flex-1">{children}</span>
      {action}
    </div>
  );
}
