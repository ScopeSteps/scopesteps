import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { ToastContext } from './toastContext';

// Long enough to read a short sentence, as in the prototype.
const TOAST_MS = 3200;

interface ToastProviderProps {
  children: ReactNode;
}

/** Shows one toast at a time in a live region, so it is announced without taking focus. */
export function ToastProvider({ children }: ToastProviderProps) {
  const [toast, setToast] = useState<{ message: string } | null>(null);
  const showToast = useCallback((message: string) => {
    setToast({ message });
  }, []);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timer = window.setTimeout(() => {
      setToast(null);
    }, TOAST_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [toast]);

  return (
    <ToastContext value={showToast}>
      {children}
      <div role="status" aria-live="polite">
        {toast && (
          <div className="fixed bottom-[calc(24px+env(safe-area-inset-bottom,0px))] left-1/2 z-40 max-w-[calc(100%-32px)] -translate-x-1/2 rounded-[10px] bg-fg px-4 py-2.5 text-[13px] text-bg shadow-pop">
            {toast.message}
          </div>
        )}
      </div>
    </ToastContext>
  );
}
