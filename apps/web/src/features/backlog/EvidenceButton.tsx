interface EvidenceButtonProps {
  /** The claim in words, for the button's accessible name. */
  about: string;
  count: number;
  onShow: () => void;
}

export function EvidenceButton({ about, count, onShow }: EvidenceButtonProps) {
  if (count === 0) {
    return <span className="text-xs text-muted">No evidence</span>;
  }
  return (
    <button
      type="button"
      onClick={onShow}
      aria-label={`Show evidence (${String(count)}) for: ${about}`}
      className="text-xs text-accent-ink underline focus-visible:outline-2 focus-visible:outline-accent"
    >
      Evidence ({count})
    </button>
  );
}
