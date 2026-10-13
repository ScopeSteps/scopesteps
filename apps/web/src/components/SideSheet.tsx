import { useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { IconButton } from './IconButton';
import { useLayer } from './useLayer';

interface SideSheetProps {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * Detail about something on the page, such as evidence or a source. Render it only while it
 * is open: mounting moves focus to the title, unmounting returns it to the opening control.
 */
export function SideSheet({ title, onClose, children, footer }: SideSheetProps) {
  const sheet = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  useLayer(sheet, { onClose, initialFocus: heading });

  return createPortal(
    <>
      <div className="fixed inset-0 z-30 bg-scrim" onClick={onClose} />
      <div
        ref={sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="fixed inset-y-0 right-0 z-[31] flex w-[min(460px,100%)] flex-col border-l border-line bg-surface shadow-pop"
      >
        <div className="flex items-center justify-between gap-2.5 border-b border-line py-3.5 pr-4 pl-5">
          <h2 id={titleId} ref={heading} tabIndex={-1} className="text-base font-semibold">
            {title}
          </h2>
          <IconButton icon="close" label="Close" onClick={onClose} />
        </div>
        <div className="flex flex-1 flex-col gap-3.5 overflow-auto px-5 py-[18px]">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </>,
    document.body,
  );
}
