import type { ButtonHTMLAttributes } from 'react';

type CitationChipProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'className'>;

/** Opens the evidence behind a claim. The label is the citation as the API names it. */
export function CitationChip(props: CitationChipProps) {
  return (
    <button
      type="button"
      className="cursor-pointer rounded border border-accent-line bg-accent-soft px-1.5 py-px font-mono text-[11px] leading-[1.6] whitespace-nowrap text-accent-ink tabular-nums hover:border-accent"
      {...props}
    />
  );
}
