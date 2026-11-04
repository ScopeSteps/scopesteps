import { describe, expect, it } from 'vitest';

import { membership, PERMISSIONS, PROJECT_ID } from '@/test/fixtures';

import { canInProject } from './permissions';
import {
  describePermissions,
  GRANTABLE_ROLES,
  isGrantableRole,
  PERMISSION_ORDER,
  roleLabelOf,
  roleName,
} from './roleNames';

const OTHER_PROJECT_ID = '019a3a5e-0000-7000-8000-0000000000aa';

describe('the roles a person can be given', () => {
  it('are Viewer, Editor and Approver, lowest first, each saying it includes the one before', () => {
    expect(GRANTABLE_ROLES.map((r) => r.label)).toEqual(['Viewer', 'Editor', 'Approver']);
    expect(GRANTABLE_ROLES[1].allows).toMatch(/^Everything a Viewer can do/);
    expect(GRANTABLE_ROLES[2].allows).toMatch(/^Everything an Editor can do/);
  });

  it('never include the admin roles', () => {
    expect(isGrantableRole('workspace_admin')).toBe(false);
    expect(roleName('integration_admin')).toBe('');
    expect(roleLabelOf('workspace_admin')).toBeNull();
    expect(roleName('approver')).toBe('Approver');
  });
});

describe('describePermissions', () => {
  it('lists every permission once', () => {
    expect(new Set(PERMISSION_ORDER).size).toBe(PERMISSION_ORDER.length);
    expect([...PERMISSION_ORDER].sort()).toEqual([...PERMISSIONS.approver].sort());
  });

  it('says what an approver can do, with nothing it cannot', () => {
    const { can, cannot } = describePermissions(PERMISSIONS.approver);

    expect(can).toContain('Approve or reject versions');
    expect(can).toContain('Chat with the agent and answer its questions');
    expect(cannot).toEqual([]);
  });

  it('tells a viewer what needs a higher role', () => {
    const { can, cannot } = describePermissions(PERMISSIONS.viewer);

    expect(can).toEqual([
      'Read the backlog, evidence and activity',
      'Start and reply to discussions',
    ]);
    expect(cannot).toContain('Chat with the agent and answer its questions');
    expect(cannot).toContain('Invite people and change their roles');
  });
});

describe('canInProject', () => {
  it('reads the role the user holds in that project only', () => {
    const memberships = [membership('viewer'), membership('approver', OTHER_PROJECT_ID)];

    expect(canInProject(memberships, PROJECT_ID, 'use_agent')).toBe(false);
    expect(canInProject(memberships, PROJECT_ID, 'read')).toBe(true);
    expect(canInProject(memberships, OTHER_PROJECT_ID, 'decide_versions')).toBe(true);
    expect(canInProject(memberships, 'not-a-member', 'read')).toBe(false);
  });
});
