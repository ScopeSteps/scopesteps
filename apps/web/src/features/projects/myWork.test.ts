import { describe, expect, it } from 'vitest';

import { hasWaitingWork, projectsWithRole, waitingGroups } from './myWork';
import type { MyWork, ProjectWork } from './myWork';

const STATUS = {
  state: 'no_baseline' as const,
  baseline_version: null,
  baseline_version_id: null,
  open_version_id: null,
};

function project(overrides: Partial<ProjectWork>): ProjectWork {
  return {
    id: 'p1',
    name: 'Library App',
    roles: ['viewer'],
    status: STATUS,
    waiting: 0,
    approver: null,
    editor: null,
    recent_activity: null,
    ...overrides,
  };
}

function work(projects: ProjectWork[]): MyWork {
  return { projects, roles: [], activity_window_days: 7 };
}

describe('waitingGroups', () => {
  it('names one of a thing in the singular and several in the plural', () => {
    const groups = waitingGroups(
      work([
        project({
          roles: ['editor'],
          editor: { open_questions: 1, draft_blockers: 2, unconfirmed_speakers: 1 },
        }),
      ]),
    );

    expect(groups.flatMap((g) => g.items.map((item) => item.text))).toEqual([
      '1 question to answer in the chat on Library App',
      '2 blockers to clear on the draft of Library App',
      '1 speaker to identify on Library App',
    ]);
  });

  it('leaves out counts of zero and groups with nothing in them', () => {
    const groups = waitingGroups(
      work([
        project({
          roles: ['approver', 'editor'],
          approver: { change_requests_in_review: 0, draft_ready_for_approval: false },
          editor: { open_questions: 0, draft_blockers: 0, unconfirmed_speakers: 0 },
        }),
      ]),
    );

    expect(groups).toEqual([]);
    expect(hasWaitingWork(groups)).toBe(false);
  });

  it('shows recent activity only where the user is a viewer, and it waits for nobody', () => {
    const activity = { events: 3, latest_at: '2026-10-28T09:00:00Z' };
    const groups = waitingGroups(
      work([
        project({ id: 'p1', roles: ['viewer'], recent_activity: activity }),
        project({ id: 'p2', name: 'Lab Bookings', roles: ['editor'], recent_activity: activity }),
      ]),
    );

    expect(groups.map((g) => g.role)).toEqual(['viewer']);
    expect(groups[0]?.items[0]).toMatchObject({ projectId: 'p1', page: 'activity' });
    expect(hasWaitingWork(groups)).toBe(false);
  });
});

describe('projectsWithRole', () => {
  it('keeps every project without a role and only matching ones with one', () => {
    const projects = [
      project({ id: 'a', roles: ['approver'] }),
      project({ id: 'b', roles: ['editor', 'approver'] }),
      project({ id: 'c', roles: ['viewer'] }),
    ];

    expect(projectsWithRole(projects, null).map((p) => p.id)).toEqual(['a', 'b', 'c']);
    expect(projectsWithRole(projects, 'approver').map((p) => p.id)).toEqual(['a', 'b']);
    expect(projectsWithRole(projects, 'viewer').map((p) => p.id)).toEqual(['c']);
  });
});
