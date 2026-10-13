import { useRef } from 'react';
import type { ReactNode, RefObject } from 'react';

import { useLayer } from '@/components/useLayer';

interface SidebarDrawerProps {
  onClose: () => void;
  initialFocus: RefObject<HTMLElement | null>;
  returnFocus: RefObject<HTMLElement | null>;
  children: ReactNode;
}

/** The sidebar as a drawer over the page, for narrow screens. Render it only while open. */
export function SidebarDrawer({
  onClose,
  initialFocus,
  returnFocus,
  children,
}: SidebarDrawerProps) {
  const drawer = useRef<HTMLDivElement>(null);
  useLayer(drawer, { onClose, initialFocus, returnFocus });

  return (
    <>
      <div className="fixed inset-0 z-30 bg-scrim" onClick={onClose} />
      <div ref={drawer} className="fixed inset-y-0 left-0 z-[35] w-[min(280px,85%)] shadow-pop">
        {children}
      </div>
    </>
  );
}
