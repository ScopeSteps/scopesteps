import { describe, expect, it } from 'vitest';

import { backlogAttention, nextStep, roleLabel, statusChip } from '@/app/shell/projectStatus';
import { BACKLOG, CANCEL_QUESTION, LENGTH_QUESTION, makeRun, PROJECT_ID } from '@/test/fixtures';

const OTHER_PROJECT_ID = '019a3a5e-0000-7000-8000-000000000009';
const PATHS = { backlogPath: '/backlog?run=1', startRunPath: '/backlog', sourcesPath: '/sources' };
const WAITING = makeRun({
  status: 'waiting_for_input',
  questions: [CANCEL_QUESTION, { ...LENGTH_QUESTION, status: 'answered' }],
});
const BLOCKER_COUNT = BACKLOG.blockers.length;

describe('roleLabel', () => {
  it.each([
    [['approver', 'editor'], 'Product owner'],
    [['editor', 'viewer'], 'Business analyst'],
    [['viewer'], 'Viewer'],
    [['workspace_admin', 'integration_admin'], null],
    [[], null],
  ] as const)('names %j in the project as %j', (roles, label) => {
    const memberships = [
      ...roles.map((role) => ({ project_id: PROJECT_ID, role })),
      { project_id: OTHER_PROJECT_ID, role: 'approver' as const },
    ];

    expect(roleLabel(memberships, PROJECT_ID)).toBe(label);
  });
});

describe('statusChip', () => {
  it.each([
    ['draft', 'Draft r1 · not approved', 'warn'],
    ['in_review', 'Draft r1 · in review', 'warn'],
    ['approved', 'Baseline approved', 'accent'],
    ['rejected', 'Draft r1 · rejected', 'neutral'],
  ] as const)('describes a %s version as "%s"', (state, text, tone) => {
    expect(statusChip(undefined, { ...BACKLOG, state }, 2)).toEqual({ text, tone });
  });

  it.each([
    ['created', 'Agent is working', 'neutral'],
    ['running', 'Agent is working', 'neutral'],
    ['waiting_for_input', 'Waiting for you', 'warn'],
    ['failed', 'Run failed', 'bad'],
    ['cancelled', 'Run stopped', 'neutral'],
  ] as const)('describes a %s run as "%s"', (status, text, tone) => {
    expect(statusChip(makeRun({ status }), undefined, 2)).toEqual({ text, tone });
  });

  it('says the project is being set up only when it has no sources', () => {
    expect(statusChip(undefined, undefined, 0)).toEqual({ text: 'Setting up', tone: 'neutral' });
    expect(statusChip(undefined, undefined, 2)).toBeNull();
    expect(statusChip(undefined, undefined, undefined)).toBeNull();
  });
});

describe('backlogAttention', () => {
  it('counts the open questions of a run that waits for the user', () => {
    expect(backlogAttention(WAITING, undefined)).toBe(1);
    expect(backlogAttention(makeRun({ status: 'running' }), undefined)).toBe(0);
  });

  it('counts the blockers the API reports on a version still under review', () => {
    expect(backlogAttention(undefined, BACKLOG)).toBe(BLOCKER_COUNT);
    expect(backlogAttention(undefined, { ...BACKLOG, state: 'approved' })).toBe(0);
  });
});

describe('nextStep', () => {
  const base = { roleLabel: 'Business analyst', run: undefined, version: undefined, ...PATHS };

  it.each([
    ['there are no sources', { sourceCount: 0 }, { label: 'Add sources', to: '/sources' }],
    [
      'sources are stored and no run is known',
      { sourceCount: 2 },
      { label: 'Start the agent run', to: '/backlog' },
    ],
    ['the sources are still loading', { sourceCount: undefined }, null],
    [
      'the agent is working',
      { sourceCount: 2, run: makeRun({ status: 'running' }) },
      { label: 'Agent is working', working: true },
    ],
    [
      'the agent waits for an answer',
      { sourceCount: 2, run: WAITING },
      { label: 'Answer 1 question', to: '/backlog?run=1' },
    ],
    [
      'the run was stopped',
      { sourceCount: 2, run: makeRun({ status: 'cancelled' }) },
      { label: 'Start a new run', to: '/backlog' },
    ],
    [
      'the draft has blockers',
      { sourceCount: 2, version: BACKLOG },
      { label: `Review ${String(BLOCKER_COUNT)} blockers`, to: '/backlog?run=1' },
    ],
    ['the draft has no blockers', { sourceCount: 2, version: { ...BACKLOG, blockers: [] } }, null],
    [
      'the baseline is approved',
      { sourceCount: 2, version: { ...BACKLOG, state: 'approved' as const } },
      null,
    ],
  ])('when %s', (_case, input, expected) => {
    expect(nextStep({ ...base, ...input })).toEqual(expected);
  });

  it('tells a viewer the project is view only, whatever its state', () => {
    expect(nextStep({ ...base, roleLabel: 'Viewer', sourceCount: 0 })).toEqual({
      label: 'View only',
    });
  });
});
