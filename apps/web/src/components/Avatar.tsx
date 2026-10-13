interface AvatarProps {
  name: string;
  size?: number;
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join('')
    .toUpperCase();
}

/** The person's initials. Decorative: the name is always shown next to it. */
export function Avatar({ name, size = 32 }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      // Computed: the avatar scales with the size it is given.
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      className="flex flex-none items-center justify-center rounded-full bg-accent-soft font-semibold text-accent-ink"
    >
      {initials(name)}
    </span>
  );
}
