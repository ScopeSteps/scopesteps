import { describe, expect, it } from 'vitest';

import { BACKLOG, STORY_ID } from '@/test/fixtures';

import { describeProblem } from './checkProblems';

const TASK_PROBLEM = 'task 019a3a5e on story 019a3a5e is a suggested task nobody accepted yet';
const REF = { item_id: STORY_ID, criterion_id: null, decision_id: null };

describe('describeProblem', () => {
  it('names an unreviewed suggested task by its story, without ids', () => {
    expect(describeProblem(TASK_PROBLEM, REF, BACKLOG, 'suggestions_reviewed')).toBe(
      'A task suggested by AI on story “Search for and book a one-off slot” is not reviewed yet',
    );
  });

  it('keeps the server’s words for another problem on a story', () => {
    expect(describeProblem('has no criteria', REF, BACKLOG, 'structure_valid')).toBe(
      'Story “Search for and book a one-off slot”: has no criteria',
    );
  });
});
