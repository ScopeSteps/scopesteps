import { createContext, useContext } from 'react';

export type ShowToast = (message: string) => void;

export const ToastContext = createContext<ShowToast | null>(null);

/**
 * Confirms an action that has already happened. Never use a toast for an error the user must
 * act on: it disappears by itself.
 */
export function useToast(): ShowToast {
  const showToast = useContext(ToastContext);
  if (!showToast) {
    throw new Error('useToast needs a ToastProvider above it');
  }
  return showToast;
}
