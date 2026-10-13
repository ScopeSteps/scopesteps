import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  /** What will appear here and how to make it appear. */
  children: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, children, action }: EmptyStateProps) {
  return (
    <div className="mx-auto my-12 flex max-w-[420px] flex-col items-center gap-2.5 text-center">
      <h2 className="text-[17px] font-semibold">{title}</h2>
      <div className="text-muted">{children}</div>
      {action}
    </div>
  );
}
