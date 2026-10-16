import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

/** How close to the bottom, in pixels, still counts as reading the newest messages. */
const NEAR_BOTTOM_PX = 64;

/**
 * Keeps a scrolling thread at its newest content while the reader is at the bottom, and leaves
 * it alone once they scroll up to read older messages. `scrollToLatest` brings them back, as
 * after sending a message.
 */
export function useStickToBottom(
  scroller: RefObject<HTMLElement | null>,
  content: RefObject<HTMLElement | null>,
) {
  // A thread opens at its newest message.
  const pinned = useRef(true);

  useEffect(() => {
    const element = scroller.current;
    if (!element) {
      return;
    }
    const onScroll = () => {
      pinned.current =
        element.scrollHeight - element.scrollTop - element.clientHeight <= NEAR_BOTTOM_PX;
    };
    element.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      element.removeEventListener('scroll', onScroll);
    };
  }, [scroller]);

  // Content grows as replies, progress and older pages arrive; follow it only while pinned, so
  // loading older messages above never pulls the reader away from what they are reading.
  useEffect(() => {
    const element = scroller.current;
    const inner = content.current;
    // jsdom has no layout, so it has no ResizeObserver either.
    if (!element || !inner || typeof ResizeObserver !== 'function') {
      return;
    }
    const observer = new ResizeObserver(() => {
      if (pinned.current) {
        element.scrollTop = element.scrollHeight;
      }
    });
    observer.observe(inner);
    return () => {
      observer.disconnect();
    };
  }, [scroller, content]);

  function scrollToLatest() {
    pinned.current = true;
    const element = scroller.current;
    if (!element) {
      return;
    }
    // After the sent message has rendered, so the bottom includes it. A jump rather than a
    // smooth scroll: scroll events during an animation would unpin the thread half way.
    requestAnimationFrame(() => {
      element.scrollTop = element.scrollHeight;
    });
  }

  return { scrollToLatest };
}
