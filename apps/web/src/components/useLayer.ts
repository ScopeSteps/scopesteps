import { useEffect, useEffectEvent, useRef } from 'react';
import type { RefObject } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Open layers, bottom to top. Escape belongs to the last one only.
const openLayers: symbol[] = [];

interface LayerOptions {
  onClose: () => void;
  /** Receives focus when the layer opens. Defaults to the layer itself. */
  initialFocus?: RefObject<HTMLElement | null>;
  /**
   * Receives focus when the layer closes. Defaults to whatever had focus when it opened;
   * name the opening control when a click may not have focused it (Safari) or when the
   * control is replaced while the layer is open.
   */
  returnFocus?: RefObject<HTMLElement | null>;
  /** Keeps Tab inside the layer. On for dialogs; off for a menu, which closes instead. */
  trapFocus?: boolean;
}

/**
 * Makes a mounted element behave as a layer over the page: focus moves into it, Escape closes
 * it only while it is the top layer, and focus returns to where it was when the layer goes
 * away, unless the user has already moved focus somewhere else.
 */
export function useLayer(
  layer: RefObject<HTMLElement | null>,
  { onClose, initialFocus, returnFocus, trapFocus = true }: LayerOptions,
): void {
  const close = useEffectEvent(onClose);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    const id = Symbol('layer');
    const element = layer.current;
    // A re-run finds focus already inside; the opener is still the one from the first run.
    if (!element?.contains(document.activeElement)) {
      opener.current = document.activeElement;
    }
    openLayers.push(id);
    (initialFocus?.current ?? element)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (openLayers.at(-1) !== id || !element) {
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab' || !trapFocus) {
        return;
      }
      const focusable = [...element.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const first = focusable.at(0);
      const last = focusable.at(-1);
      if (!first || !last) {
        event.preventDefault();
        return;
      }
      const active = document.activeElement;
      const outside = !element.contains(active) || !focusable.some((item) => item === active);
      if (event.shiftKey && (outside || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (outside || active === last)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      openLayers.splice(openLayers.indexOf(id), 1);
      // Still in the page: the effect is re-running (StrictMode does so on mount), not closing.
      // Moving focus out now would make a menu that closes on blur close itself.
      if (element?.isConnected) {
        return;
      }
      const active = document.activeElement;
      const focusWasLeftBehind =
        active === null || active === document.body || (element?.contains(active) ?? false);
      // Read now, not when the layer opened: the control may have been replaced since.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      const target = returnFocus?.current ?? opener.current;
      if (focusWasLeftBehind && target instanceof HTMLElement && target.isConnected) {
        target.focus();
      }
    };
  }, [layer, initialFocus, returnFocus, trapFocus]);
}
