import type { components } from '@scopesteps/api-client';

type Role = components['schemas']['Role'];

export interface RolePermissions {
  can: string[];
  cannot: string[];
}

const EDITOR_CAN = [
  'Chat with the agent and edit drafts',
  'Add and remove sources',
  'Correct people and decision rights',
];

/**
 * What the given roles allow in a project, as the API enforces it. Roles combine and none
 * implies another, so an approver without the editor role cannot edit drafts.
 */
export function permissionsFor(roles: readonly Role[]): RolePermissions {
  const editor = roles.includes('editor');
  const approver = roles.includes('approver');
  const can = ['Read the backlog, evidence and activity', 'Export approved versions'];
  const cannot: string[] = [];
  if (editor) {
    can.push(...EDITOR_CAN);
  } else {
    cannot.push('Edit drafts, sources or people');
  }
  if (editor || approver) {
    can.push('Make scope decisions on a draft');
  } else {
    cannot.push('Make scope decisions');
  }
  if (approver) {
    can.push('Approve or reject versions');
  } else {
    cannot.push('Approve or reject versions');
  }
  return { can, cannot };
}
