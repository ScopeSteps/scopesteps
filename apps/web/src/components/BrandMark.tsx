interface BrandMarkProps {
  size?: number;
}

/** The ScopeSteps mark: a magnifier over three steps, the steps in the accent colour. */
export function BrandMark({ size = 22 }: BrandMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="flex-none">
      <circle cx="14" cy="14" r="10.5" fill="none" stroke="currentColor" strokeWidth="3" />
      <path d="M22 22l7 7" stroke="currentColor" strokeWidth="3.6" strokeLinecap="round" />
      <path
        d="M8.5 18.5h3.5v-3.5h3.5v-3.5h3.5"
        fill="none"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent"
      />
    </svg>
  );
}
