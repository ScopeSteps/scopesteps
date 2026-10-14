import type { ReactNode } from 'react';

/** Something that happened to the run, as a quiet line across the thread. */
export function ChatEvent({ children }: { children: ReactNode }) {
  return (
    <div
      role="note"
      className="flex items-center gap-3 text-center text-xs text-subtle before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line"
    >
      {children}
    </div>
  );
}
