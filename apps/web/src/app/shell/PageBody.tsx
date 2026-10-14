import type { ReactNode } from 'react';

interface PageBodyProps {
  children: ReactNode;
}

/** The centred column every page lays its content out in. */
export function PageBody({ children }: PageBodyProps) {
  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-4 px-6 pt-6 pb-14 max-wide:px-4">
      {children}
    </div>
  );
}
