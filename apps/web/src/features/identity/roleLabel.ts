import type { components } from '@scopesteps/api-client';

type Role = components['schemas']['Role'];

// Most senior first. The admin roles are not shown in the POC.
const SHOWN_ROLES: readonly { role: Role; label: string }[] = [
  { role: 'approver', label: 'Product owner' },
  { role: 'editor', label: 'Business analyst' },
  { role: 'viewer', label: 'Viewer' },
];

/** The name the app gives the most senior role among `roles`, or null for none it shows. */
export function roleLabelFor(roles: readonly Role[]): string | null {
  return SHOWN_ROLES.find(({ role }) => roles.includes(role))?.label ?? null;
}
