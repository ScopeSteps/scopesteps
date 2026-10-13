interface BadgeProps {
  count: number;
  /** Read out in place of the bare number: "3 need attention". */
  label: string;
}

/** A count on a navigation item. Renders nothing for zero. */
export function Badge({ count, label }: BadgeProps) {
  if (count <= 0) {
    return null;
  }
  return (
    <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-[5px] text-[11px] font-bold text-accent-fg">
      <span aria-hidden="true">{count}</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
