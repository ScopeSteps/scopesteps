import type { ReactNode } from 'react';

const PATHS = {
  backlog: (
    <>
      <path d="M8 5.5h8M8 10h8M8 14.5h8" />
      <path d="M4 5.5h.01M4 10h.01M4 14.5h.01" strokeWidth="2.4" />
    </>
  ),
  sources: (
    <>
      <path d="M6 2.8h5.6L15 6.2v11H6z" />
      <path d="M11.4 2.8v3.6H15" />
    </>
  ),
  activity: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6.2V10l2.6 1.8" />
    </>
  ),
  menu: <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />,
  close: <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />,
  right: <path d="M8 5.5l4.5 4.5L8 14.5" />,
  up: <path d="M6 12l4-4 4 4" />,
  settings: (
    <>
      <path d="M4 6.5h7M15 6.5h1M4 13.5h2M10 13.5h6" />
      <circle cx="13" cy="6.5" r="2" />
      <circle cx="8" cy="13.5" r="2" />
    </>
  ),
  info: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 9v4.5M10 6.6v.1" />
    </>
  ),
  warn: (
    <>
      <path d="M10 3.5l7 12.5H3z" />
      <path d="M10 8.5v3.2M10 13.8v.1" />
    </>
  ),
  sun: (
    <>
      <circle cx="10" cy="10" r="3.2" />
      <path d="M10 2.5v1.6M10 15.9v1.6M2.5 10h1.6M15.9 10h1.6M4.7 4.7l1.1 1.1M14.2 14.2l1.1 1.1M4.7 15.3l1.1-1.1M14.2 5.8l1.1-1.1" />
    </>
  ),
  moon: <path d="M15.5 12A6.5 6.5 0 018 4.5a6.5 6.5 0 107.5 7.5z" />,
  monitor: (
    <>
      <rect x="3" y="4" width="14" height="9.5" rx="1.5" />
      <path d="M7.5 16.5h5M10 13.5v3" />
    </>
  ),
  panel: (
    <>
      <rect x="3" y="4" width="14" height="12" rx="2" />
      <path d="M8 4v12" />
    </>
  ),
  chat: (
    <path d="M4 5.5A2.5 2.5 0 016.5 3h7A2.5 2.5 0 0116 5.5v5a2.5 2.5 0 01-2.5 2.5H9.2L6 15.8V13h0A2.5 2.5 0 014 10.5z" />
  ),
  plus: <path d="M10 4.5v11M4.5 10h11" />,
  send: <path d="M10 15.5v-11M5.5 9l4.5-4.5L14.5 9" />,
  stop: <rect x="6" y="6" width="8" height="8" rx="1.6" fill="currentColor" stroke="none" />,
  upload: <path d="M10 13V4M6 7.5l4-4 4 4M4 13.5V16h12v-2.5" />,
  check: <path d="M4.5 10.5l3.5 3.5 7.5-8" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  size?: number;
}

/** A decorative line icon. The control around it carries the accessible name. */
export function Icon({ name, size = 18 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="flex-none"
    >
      {PATHS[name]}
    </svg>
  );
}
