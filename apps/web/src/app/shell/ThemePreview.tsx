import type { Theme } from '@/lib/preferences';

interface ThemePreviewProps {
  theme: Theme;
}

/** A miniature of the theme: its page and surface colours, forced with `data-theme`. */
export function ThemePreview({ theme }: ThemePreviewProps) {
  const [left, right] = theme === 'system' ? ['light', 'dark'] : [theme, theme];
  return (
    <span
      aria-hidden="true"
      className="flex h-[52px] overflow-hidden rounded-md border border-line"
    >
      <span data-theme={left} className="flex-1 bg-bg" />
      <span
        data-theme={right}
        className={theme === 'system' ? 'flex-1 bg-bg' : 'flex-2 bg-surface'}
      />
    </span>
  );
}
