import type { ReactNode } from 'react';

import { BrandMark } from '@/components/BrandMark';

/** A message from the agent in the thread, behind the ScopeSteps mark. */
export function AgentMessage({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
      <span className="flex size-7 items-center justify-center rounded-lg bg-accent-soft text-accent-ink">
        <BrandMark size={16} mono />
      </span>
      <div className="flex min-w-0 flex-col gap-2.5 pt-[3px] text-[15px] leading-[1.6]">
        {children}
      </div>
    </div>
  );
}
