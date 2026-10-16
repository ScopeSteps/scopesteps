interface SectionHeadingProps {
  id: string;
  title: string;
  /** How many entries the section lists right now. */
  count: number;
}

/** A backlog section's heading with the number of entries listed under it. */
export function SectionHeading({ id, title, count }: SectionHeadingProps) {
  return (
    <h3
      id={id}
      className="flex items-center gap-2 px-0.5 pt-2 text-xs font-semibold tracking-[0.06em] text-subtle uppercase"
    >
      {title} <span className="font-mono tracking-normal tabular-nums">{count}</span>
    </h3>
  );
}
