/** The show or hide control inside a password field's right edge. */
export function PasswordToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={shown}
      aria-label={shown ? 'Hide password' : 'Show password'}
      onClick={onToggle}
      className="min-h-7 cursor-pointer rounded-md px-2 text-[13px] font-semibold text-accent-ink"
    >
      {shown ? 'Hide' : 'Show'}
    </button>
  );
}
