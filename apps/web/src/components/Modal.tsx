import { useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { cx } from '@/lib/cx';

import { IconButton } from './IconButton';
import { useLayer } from './useLayer';

interface ModalProps {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  /** Actions, right-aligned under the body. */
  footer?: ReactNode;
  /** A wider, fixed-height modal for content with its own navigation. */
  wide?: boolean;
  /** The children lay themselves out edge to edge instead of in the padded body. */
  flush?: boolean;
}

/**
 * A decision or a short form over the page. Render it only while it is open: mounting moves
 * focus to the title, unmounting returns it to the control that opened the modal.
 */
export function Modal({
  title,
  onClose,
  children,
  footer,
  wide = false,
  flush = false,
}: ModalProps) {
  const dialog = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  useLayer(dialog, { onClose, initialFocus: heading });

  return createPortal(
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-scrim p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cx(
          'flex max-h-[calc(100%-32px)] flex-col rounded-[14px] border border-line bg-surface shadow-pop',
          wide ? 'h-[min(600px,calc(100%-32px))] w-[min(760px,100%)]' : 'w-[min(560px,100%)]',
        )}
      >
        <div className="flex items-center justify-between gap-2.5 border-b border-line py-3.5 pr-4 pl-5">
          <h2 id={titleId} ref={heading} tabIndex={-1} className="text-base font-semibold">
            {title}
          </h2>
          <IconButton icon="close" label="Close" onClick={onClose} />
        </div>
        {flush ? (
          children
        ) : (
          <div className="flex flex-1 flex-col gap-3.5 overflow-auto px-5 py-[18px]">
            {children}
          </div>
        )}
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
