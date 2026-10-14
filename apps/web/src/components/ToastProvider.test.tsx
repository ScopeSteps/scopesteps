import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Button } from '@/components/Button';
import { useToast } from '@/components/toastContext';
import { ToastProvider } from '@/components/ToastProvider';

function SaveButton() {
  const showToast = useToast();
  return (
    <Button
      onClick={() => {
        showToast('Settings saved.');
      }}
    >
      Save
    </Button>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('ToastProvider', () => {
  it('announces the message in a polite live region without moving focus', () => {
    render(
      <ToastProvider>
        <SaveButton />
      </ToastProvider>,
    );
    const save = screen.getByRole('button', { name: 'Save' });
    save.focus();

    fireEvent.click(save);

    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveTextContent('Settings saved.');
    expect(save).toHaveFocus();
  });

  it('removes the toast by itself after a few seconds', () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <SaveButton />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('fails loudly when used outside its provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => render(<SaveButton />)).toThrow('useToast needs a ToastProvider above it');
  });
});
