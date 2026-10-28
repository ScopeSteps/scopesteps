import type { components } from '@scopesteps/api-client';

type Role = components['schemas']['Role'];

/** The roles a person can be given in a project, with what each allows, in plain words. */
export const GRANTABLE_ROLES = [
  { role: 'viewer', label: 'Viewer', allows: 'Can look at everything in the project.' },
  {
    role: 'editor',
    label: 'Editor',
    allows: 'Can work on sources, the backlog and the chat.',
  },
  {
    role: 'approver',
    label: 'Approver',
    allows: 'Makes decisions, approves scope and manages members.',
  },
] as const satisfies readonly { role: Role; label: string; allows: string }[];

export type GrantableRole = (typeof GRANTABLE_ROLES)[number]['role'];

/** "Viewer", "Editor and Approver": the roles among `roles` the app shows, in a fixed order. */
export function roleNames(roles: readonly Role[]): string {
  const names = GRANTABLE_ROLES.filter(({ role }) => roles.includes(role)).map((r) => r.label);
  return names.length <= 1
    ? (names[0] ?? '')
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1] ?? ''}`;
}
