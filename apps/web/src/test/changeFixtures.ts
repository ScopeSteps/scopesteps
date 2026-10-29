import type { components } from '@scopesteps/api-client';
import { http, HttpResponse } from 'msw';

import {
  APPROVER,
  BACKLOG,
  PROJECT,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  STORY_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  versionSummary,
} from '@/test/fixtures';
import { API, CHANGE_REQUESTS_URL, VERSIONS_URL } from '@/test/handlers';

type Schemas = components['schemas'];

/** Synthetic change-request data: CR-3 asks for weekly bookings against baseline v1. */
export const BASELINE_ID = '019a3a5e-0000-7000-8000-0000000000e2';
export const CANDIDATE_ID = '019a3a5e-0000-7000-8000-0000000000e3';
export const CHANGE_REQUEST_ID = '019a3a5e-0000-7000-8000-0000000000d9';
export const CHANGE_RUN_ID = '019a3a5e-0000-7000-8000-0000000000f9';
export const SCOPE_DECISION_ID = '019a3a5e-0000-7000-8000-000000000309';
export const APPROVER_ID = '019a3a5e-0000-7000-8000-000000000003';
export const SCOPE_DECISION_URL = `${API}/backlogs/${CANDIDATE_ID}/scope-decisions/${SCOPE_DECISION_ID}`;
export const CANDIDATE_URL = `${VERSIONS_URL}/${CANDIDATE_ID}`;
export const CHANGE_SET_URL = `${API}/backlogs/${CANDIDATE_ID}/change-set`;

const [EPIC, STORY] = BACKLOG.items;
if (!EPIC || !STORY) {
  throw new Error('The backlog fixture needs an epic and a story.');
}

const EXCLUSION_QUOTE = 'Recurring reservations are out of scope for release one.';
export const EXCLUSION_EVIDENCE: Schemas['EvidenceRef'] = {
  source_version_id: TRANSCRIPT.id,
  block_id: TRANSCRIPT_BLOCKS[1]?.id ?? '',
  quote: EXCLUSION_QUOTE,
  relationship: 'supporting',
};

const BASE_STORY: Schemas['BacklogItem'] = { ...STORY, blockers: [], criteria: [] };
export const CHANGED_STORY: Schemas['BacklogItem'] = {
  ...BASE_STORY,
  title: 'Search for and book a one-off or weekly slot',
};
export const UNCHANGED_STORY: Schemas['BacklogItem'] = {
  ...BASE_STORY,
  id: '019a3a5e-0000-7000-8000-00000000a105',
  title: 'See a room’s capacity before booking',
};
export const ADDED_STORY: Schemas['BacklogItem'] = {
  ...BASE_STORY,
  id: '019a3a5e-0000-7000-8000-00000000a106',
  title: 'Book a weekly recurring reservation',
};
export const REMOVED_STORY: Schemas['BacklogItem'] = {
  ...BASE_STORY,
  id: '019a3a5e-0000-7000-8000-00000000a107',
  title: 'Print a booking receipt',
};

export const SCOPE_DECISION: Schemas['BacklogDecision'] = {
  id: SCOPE_DECISION_ID,
  kind: 'scope_reversal',
  status: 'open',
  subject: 'Recurring reservations',
  question: 'Reverse the exclusion of recurring reservations?',
  why_it_matters: 'The baseline excludes recurring reservations.',
  evidence: [EXCLUSION_EVIDENCE],
  affected_item_ids: [ADDED_STORY.id],
  question_id: null,
  answer: null,
  decided_by: null,
  decided_at: null,
};

/** CR-3's candidate in review: one story changed, one added, one removed, one untouched. */
export const CANDIDATE: Schemas['BacklogVersionResponse'] = {
  ...BACKLOG,
  id: CANDIDATE_ID,
  base_version_id: BASELINE_ID,
  state: 'in_review',
  revision: 1,
  run_id: CHANGE_RUN_ID,
  items: [{ ...EPIC, blockers: [] }, CHANGED_STORY, UNCHANGED_STORY, ADDED_STORY],
  decisions: [SCOPE_DECISION],
  out_of_scope: [],
  blockers: [],
};

/** The candidate after an approver records `outcome` on its scope decision. */
export function decidedCandidate(outcome: 'reverse' | 'keep'): Schemas['BacklogVersionResponse'] {
  return {
    ...CANDIDATE,
    revision: 2,
    decisions: [
      {
        ...SCOPE_DECISION,
        status: 'answered',
        answer: outcome,
        decided_by: APPROVER_ID,
        decided_at: '2026-10-15T11:00:00Z',
      },
    ],
  };
}

export const CHANGE_SET: Schemas['ChangeSetResponse'] = {
  id: '019a3a5e-0000-7000-8000-0000000000d8',
  change_request_id: CHANGE_REQUEST_ID,
  base_version_id: BASELINE_ID,
  base_content_hash: BACKLOG.content_hash,
  candidate_version_id: CANDIDATE_ID,
  candidate_content_hash: 'c'.repeat(64),
  operations: [
    {
      kind: 'modify_item',
      item_id: STORY_ID,
      before: BASE_STORY,
      after: CHANGED_STORY,
      changed_fields: ['title'],
      criteria: [],
      rationale: 'The request asks for weekly slots.',
    },
    {
      kind: 'add_item',
      item_id: ADDED_STORY.id,
      before: null,
      after: ADDED_STORY,
      changed_fields: [],
      criteria: [],
      rationale: 'Clubs need the same room every week.',
    },
    {
      kind: 'remove_item',
      item_id: REMOVED_STORY.id,
      before: REMOVED_STORY,
      after: null,
      changed_fields: [],
      criteria: [],
      rationale: 'Receipts are replaced by the confirmation email.',
    },
  ],
  removed_exclusions: [{ summary: EXCLUSION_QUOTE, evidence: [EXCLUSION_EVIDENCE] }],
  scope_decisions: [
    {
      decision_id: SCOPE_DECISION_ID,
      reverses: 'exclusion',
      reversed_decision_id: null,
      summary: EXCLUSION_QUOTE,
    },
  ],
  open_decision_ids: [SCOPE_DECISION_ID],
  impacts: [],
};

/** CR-3's impact as the server counts it from the baseline and the candidate. */
export const IMPACT: Schemas['ChangeImpactResponse'] = {
  epics: { before: 1, after: 1, added: 0, changed: 0, removed: 0, unchanged: 1 },
  stories: { before: 3, after: 3, added: 1, changed: 1, removed: 1, unchanged: 1 },
  criteria: { before: 0, after: 0, added: 0, changed: 0, removed: 0, unchanged: 0 },
  scope_decisions: 1,
};

export function changeRequest(
  overrides: Partial<Schemas['ChangeRequestResponse']> = {},
): Schemas['ChangeRequestResponse'] {
  return {
    id: CHANGE_REQUEST_ID,
    number: 3,
    project_id: PROJECT_ID,
    text: 'Clubs want to book the same room every week.',
    requested_by: { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
    requested_at: '2026-10-15T09:00:00Z',
    base_version_id: BASELINE_ID,
    base_version_number: 1,
    base_content_hash: BACKLOG.content_hash,
    source_version_id: '019a3a5e-0000-7000-8000-0000000000b9',
    run_id: CHANGE_RUN_ID,
    status: 'in_review',
    candidate_version_id: CANDIDATE_ID,
    summary: { added: 1, changed: 1, removed: 1 },
    impact: IMPACT,
    analysis: 'Weekly bookings bring back recurring reservations, which v1 excludes.',
    failure: null,
    analyzed_at: '2026-10-15T09:01:00Z',
    approved_version_number: null,
    ...overrides,
  };
}

/**
 * A project with baseline v1 and CR-3's candidate in review, seen by `user`; the approver is a
 * member too. Override any route with `server.use`.
 */
export function candidateHandlers(user: Schemas['CurrentUserResponse'] = REVIEWER) {
  return [
    http.get(`${API}/me`, () => HttpResponse.json(user)),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        status: {
          state: 'candidate_in_review',
          baseline_version: 1,
          baseline_version_id: BASELINE_ID,
          open_version_id: CANDIDATE_ID,
        },
      }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/members`, () =>
      HttpResponse.json({
        members: [
          {
            user_id: REVIEWER_ID,
            display_name: REVIEWER.display_name,
            job_title: '',
            roles: ['editor'],
          },
          {
            user_id: APPROVER_ID,
            display_name: APPROVER.display_name,
            job_title: '',
            roles: ['approver'],
          },
        ],
      }),
    ),
    http.get(VERSIONS_URL, () =>
      HttpResponse.json({
        versions: [
          versionSummary(CANDIDATE_ID, {
            state: 'in_review',
            base_version_id: BASELINE_ID,
            run_id: CHANGE_RUN_ID,
          }),
          versionSummary(BASELINE_ID, { number: 1 }),
        ],
        next_cursor: null,
      }),
    ),
    http.get(CANDIDATE_URL, () => HttpResponse.json(CANDIDATE)),
    http.get(CHANGE_SET_URL, () => HttpResponse.json(CHANGE_SET)),
    http.get(`${API}/change-requests/${CHANGE_REQUEST_ID}`, () =>
      HttpResponse.json(changeRequest()),
    ),
    http.get(CHANGE_REQUESTS_URL, () =>
      HttpResponse.json({ change_requests: [changeRequest()], next_cursor: null }),
    ),
  ];
}
