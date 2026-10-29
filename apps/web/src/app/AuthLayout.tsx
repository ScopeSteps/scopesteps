import { useId } from 'react';
import type { ReactNode } from 'react';

import { BrandMark } from '@/components/BrandMark';

interface AuthLayoutProps {
  title: string;
  /** One line under the title. */
  intro?: ReactNode;
  children: ReactNode;
  /** Under the card, such as a link to the other account page. */
  footer?: ReactNode;
}

/** The frame of the pages a person reaches without a session: one card, no navigation. */
export function AuthLayout({ title, intro, children, footer }: AuthLayoutProps) {
  const titleId = useId();
  return (
    <main
      aria-labelledby={titleId}
      className="flex min-h-full items-center justify-center bg-bg px-4 py-8"
    >
      <div className="flex w-[min(400px,100%)] flex-col gap-5">
        <p className="flex items-center justify-center gap-2 text-lg font-bold tracking-[-0.01em]">
          <BrandMark size={28} />
          ScopeSteps
        </p>
        <div className="flex flex-col gap-3.5 rounded-2xl border border-line bg-surface p-6">
          <div className="flex flex-col gap-1">
            <h1 id={titleId} className="text-[22px] font-semibold tracking-[-0.01em]">
              {title}
            </h1>
            {intro && <p className="text-muted">{intro}</p>}
          </div>
          {children}
        </div>
        {footer && <p className="text-center text-[13px] text-muted">{footer}</p>}
      </div>
    </main>
  );
}
