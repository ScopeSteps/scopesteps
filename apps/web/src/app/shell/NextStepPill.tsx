import { Link } from 'react-router';

import { Icon } from '@/components/Icon';

import type { NextStep } from './projectStatus';

const PILL_CLASSES =
  'inline-flex min-h-8 items-center gap-1.5 rounded-full border border-accent-line bg-accent-soft px-3 text-[13px] font-semibold whitespace-nowrap text-accent-ink';
const WORKING_DOT_DELAYS = ['', '[animation-delay:150ms]', '[animation-delay:300ms]'];

interface NextStepPillProps {
  step: NextStep;
}

/** The next thing to do in the project: a link when the user can do it, a note when not. */
export function NextStepPill({ step }: NextStepPillProps) {
  if (step.to) {
    return (
      <Link to={step.to} className={`${PILL_CLASSES} hover:border-accent`}>
        <span aria-hidden="true" className="size-[7px] rounded-full bg-accent" />
        {step.label}
        <Icon name="right" size={14} />
      </Link>
    );
  }
  return (
    <span className={PILL_CLASSES}>
      {step.working && (
        <span aria-hidden="true" className="flex gap-1">
          {WORKING_DOT_DELAYS.map((delay) => (
            <span
              key={delay}
              className={`size-1.5 animate-working rounded-full bg-accent ${delay}`}
            />
          ))}
        </span>
      )}
      {step.label}
    </span>
  );
}
