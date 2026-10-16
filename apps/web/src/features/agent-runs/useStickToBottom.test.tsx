import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useStickToBottom } from './useStickToBottom';

// jsdom has no layout: the test sets the sizes a browser would measure.
const VIEW_HEIGHT = 400;
let contentHeight = 1000;
let resized: () => void = () => undefined;

class FakeResizeObserver {
  constructor(callback: () => void) {
    resized = callback;
  }
  observe() {
    return undefined;
  }
  disconnect() {
    return undefined;
  }
}

function Thread() {
  const scroller = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const { scrollToLatest } = useStickToBottom(scroller, content);
  return (
    <>
      <div ref={scroller} role="region" aria-label="Thread">
        <div ref={content} />
      </div>
      <button type="button" onClick={scrollToLatest}>
        Send
      </button>
    </>
  );
}

function renderThread() {
  render(<Thread />);
  const thread = screen.getByRole('region', { name: 'Thread' });
  Object.defineProperty(thread, 'scrollHeight', { get: () => contentHeight });
  Object.defineProperty(thread, 'clientHeight', { get: () => VIEW_HEIGHT });
  return thread;
}

function scrollTo(thread: HTMLElement, top: number) {
  thread.scrollTop = top;
  fireEvent.scroll(thread);
}

function grow(height: number) {
  contentHeight = height;
  act(() => {
    resized();
  });
}

describe('useStickToBottom', () => {
  beforeEach(() => {
    contentHeight = 1000;
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens at the newest message and follows new content while the reader is at the bottom', () => {
    const thread = renderThread();

    grow(1000);
    expect(thread.scrollTop).toBe(1000);

    grow(1300);
    expect(thread.scrollTop).toBe(1300);
  });

  it('stays where the reader scrolled up to when new content arrives', () => {
    const thread = renderThread();
    grow(1000);

    scrollTo(thread, 100);
    grow(1300);

    expect(thread.scrollTop).toBe(100);
  });

  it('brings a reader who scrolled up back to the newest message when they send', async () => {
    const thread = renderThread();
    grow(1000);
    scrollTo(thread, 100);

    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(thread.scrollTop).toBe(1000);
    grow(1200);
    expect(thread.scrollTop).toBe(1200);
  });
});
