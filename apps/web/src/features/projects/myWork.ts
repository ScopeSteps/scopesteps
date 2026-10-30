import type { components } from '@scopesteps/api-client';

import { roleLabelOf } from '@/features/identity';

type Schemas = components['schemas'];
export type MyWork = Schemas['MyWorkResponse'];
export type ProjectWork = Schemas['ProjectWorkResponse'];
export type SummaryRole = Schemas['Role'];

/** The pages a waiting item can send the user to; the app turns them into paths. */
export type WorkPage = 'changes' | 'backlog' | 'chat' | 'people' | 'activity';

export interface WaitingItem {
  key: string;
  text: string;
  projectId: string;
  page: WorkPage;
}

export interface WaitingGroup {
  role: SummaryRole;
  title: string;
  items: WaitingItem[];
}

function count(n: number, one: string, many: string): string {
  return `${String(n)} ${n === 1 ? one : many}`;
}

function approverItems(project: ProjectWork): WaitingItem[] {
  const work = project.approver;
  if (!work) {
    return [];
  }
  const items: WaitingItem[] = [];
  if (work.change_requests_in_review > 0) {
    items.push({
      key: `${project.id}:changes`,
      text: `${count(work.change_requests_in_review, 'change', 'changes')} waiting for your decision on ${project.name}`,
      projectId: project.id,
      page: 'changes',
    });
  }
  if (work.draft_ready_for_approval) {
    items.push({
      key: `${project.id}:approve`,
      text: `The draft on ${project.name} is ready for your approval`,
      projectId: project.id,
      page: 'backlog',
    });
  }
  return items;
}

function editorItems(project: ProjectWork): WaitingItem[] {
  const work = project.editor;
  if (!work) {
    return [];
  }
  const items: WaitingItem[] = [];
  if (work.open_questions > 0) {
    items.push({
      key: `${project.id}:questions`,
      text: `${count(work.open_questions, 'question', 'questions')} to answer in the chat on ${project.name}`,
      projectId: project.id,
      page: 'chat',
    });
  }
  if (work.draft_blockers > 0) {
    items.push({
      key: `${project.id}:blockers`,
      text: `${count(work.draft_blockers, 'blocker', 'blockers')} to clear on the draft of ${project.name}`,
      projectId: project.id,
      page: 'backlog',
    });
  }
  if (work.unconfirmed_speakers > 0) {
    items.push({
      key: `${project.id}:speakers`,
      text: `${count(work.unconfirmed_speakers, 'speaker', 'speakers')} to identify on ${project.name}`,
      projectId: project.id,
      page: 'people',
    });
  }
  return items;
}

function viewerItems(project: ProjectWork, days: number): WaitingItem[] {
  const activity = project.recent_activity;
  if (!activity || !project.roles.includes('viewer')) {
    return [];
  }
  return [
    {
      key: `${project.id}:activity`,
      text: `${count(activity.events, 'update', 'updates')} on ${project.name} in the last ${count(days, 'day', 'days')}`,
      projectId: project.id,
      page: 'activity',
    },
  ];
}

/**
 * What waits for the user, by role, in the API's project order. Each project carries only the
 * work its roles allow, so a viewer never gets an approver's or editor's item.
 */
export function waitingGroups(work: MyWork): WaitingGroup[] {
  const groups: WaitingGroup[] = [
    {
      role: 'approver',
      title: roleLabelOf('approver') ?? 'Approver',
      items: work.projects.flatMap(approverItems),
    },
    {
      role: 'editor',
      title: roleLabelOf('editor') ?? 'Editor',
      items: work.projects.flatMap(editorItems),
    },
    {
      role: 'viewer',
      title: 'Recent activity',
      items: work.projects.flatMap((p) => viewerItems(p, work.activity_window_days)),
    },
  ];
  return groups.filter((group) => group.items.length > 0);
}

/** Activity is shown but waits for nobody. */
export function hasWaitingWork(groups: readonly WaitingGroup[]): boolean {
  return groups.some((group) => group.role !== 'viewer');
}

export function projectsWithRole(
  projects: readonly ProjectWork[],
  role: SummaryRole | null,
): ProjectWork[] {
  return role === null ? [...projects] : projects.filter((p) => p.roles.includes(role));
}
