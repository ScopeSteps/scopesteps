import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];

/** Synthetic room-booking data shared by feature tests. */
export const PROJECT_ID = '019a3a5e-0000-7000-8000-000000000001';
export const REVIEWER_ID = '019a3a5e-0000-7000-8000-000000000002';
export const RUN_ID = '019a3a5e-0000-7000-8000-0000000000f1';
export const VERSION_ID = '019a3a5e-0000-7000-8000-0000000000e1';

export const REVIEWER: Schemas['CurrentUserResponse'] = {
  id: REVIEWER_ID,
  email: 'reviewer@scopesteps.local',
  display_name: 'Local Reviewer',
  job_title: '',
  about: '',
  revision: 1,
  memberships: [{ project_id: PROJECT_ID, role: 'editor' }],
};

export const BRIEF: Schemas['SourceVersionResponse'] = {
  id: '019a3a5e-0000-7000-8000-0000000000b1',
  source_id: '019a3a5e-0000-7000-8000-0000000000a1',
  project_id: PROJECT_ID,
  kind: 'brief',
  version: 1,
  filename: 'brief.md',
  media_type: 'text/markdown',
  checksum_sha256: 'a'.repeat(64),
  word_count: 30,
  block_count: 2,
  created_at: '2026-10-12T09:00:00Z',
};
export const TRANSCRIPT: Schemas['SourceVersionResponse'] = {
  ...BRIEF,
  id: '019a3a5e-0000-7000-8000-0000000000b2',
  source_id: '019a3a5e-0000-7000-8000-0000000000a2',
  kind: 'transcript',
  filename: 'transcript.md',
  block_count: 2,
};

export const BRIEF_BLOCKS: Schemas['SourceBlockResponse'][] = [
  {
    id: '019a3a5e-0000-7000-8000-0000000000c1',
    source_version_id: BRIEF.id,
    ordinal: 1,
    text: '# Campus Room Booking',
    locator: { paragraph: 1, start_offset: 0, end_offset: 21 },
  },
  {
    id: '019a3a5e-0000-7000-8000-0000000000c2',
    source_version_id: BRIEF.id,
    ordinal: 2,
    text: 'A user can search rooms by date, time and capacity. A booking can last up to 4 hours.',
    locator: { paragraph: 2, start_offset: 23, end_offset: 108 },
  },
];
export const TRANSCRIPT_BLOCKS: Schemas['SourceBlockResponse'][] = [
  {
    id: '019a3a5e-0000-7000-8000-0000000000c3',
    source_version_id: TRANSCRIPT.id,
    ordinal: 1,
    text: '**Dana (Facilities):** Three hours is the most I want for a single booking.',
    locator: { paragraph: 1, start_offset: 0, end_offset: 75 },
  },
  {
    id: '019a3a5e-0000-7000-8000-0000000000c4',
    source_version_id: TRANSCRIPT.id,
    ordinal: 2,
    text: '**Alex (Product owner):** Recurring reservations are out of scope for release one.',
    locator: { paragraph: 2, start_offset: 77, end_offset: 159 },
  },
];

const FOUR_HOURS: Schemas['EvidenceRef'] = {
  source_version_id: BRIEF.id,
  block_id: '019a3a5e-0000-7000-8000-0000000000c2',
  quote: 'A booking can last up to 4 hours.',
  relationship: 'conflicting',
};
const THREE_HOURS: Schemas['EvidenceRef'] = {
  source_version_id: TRANSCRIPT.id,
  block_id: '019a3a5e-0000-7000-8000-0000000000c3',
  // As a model quotes it: without the transcript's markdown emphasis.
  quote: 'Dana (Facilities): Three hours is the most I want for a single booking.',
  relationship: 'conflicting',
};

export const CANCEL_QUESTION: Schemas['ClarificationQuestion'] = {
  id: '019a3a5e-0000-7000-8000-0000000000d1',
  subject: 'Cancellation and no-shows',
  text: 'How late may a user cancel a booking?',
  why_it_matters: 'The sources leave the cancellation rule open.',
  evidence_block_ids: ['019a3a5e-0000-7000-8000-0000000000c2'],
  evidence: [
    {
      source_version_id: BRIEF.id,
      block_id: '019a3a5e-0000-7000-8000-0000000000c2',
      relationship: 'supporting',
    },
  ],
  status: 'open',
  round: 1,
  answer: null,
  answered_by: null,
  answered_at: null,
};
export const LENGTH_QUESTION: Schemas['ClarificationQuestion'] = {
  ...CANCEL_QUESTION,
  id: '019a3a5e-0000-7000-8000-0000000000d2',
  subject: 'Maximum booking length',
  text: 'Is the maximum booking length four hours or three hours?',
  why_it_matters: 'The brief and the transcript disagree.',
  evidence_block_ids: ['019a3a5e-0000-7000-8000-0000000000c3'],
  evidence: [
    {
      source_version_id: TRANSCRIPT.id,
      block_id: '019a3a5e-0000-7000-8000-0000000000c3',
      relationship: 'supporting',
    },
  ],
};
export const CANCEL_ANSWER = 'Users can cancel up to one hour before the start.';

export function makeRun(overrides: Partial<Schemas['RunResponse']> = {}): Schemas['RunResponse'] {
  return {
    id: RUN_ID,
    project_id: PROJECT_ID,
    mode: 'initial',
    status: 'created',
    stage: 'explore',
    revision: 1,
    source_version_ids: [BRIEF.id, TRANSCRIPT.id],
    provider: 'gemini',
    model_id: 'test-model',
    fallback_reason: null,
    prompt_version: 'explore-v1,draft-v4',
    usage: {
      model_turns: 0,
      tool_calls: 0,
      clarification_rounds: 0,
      input_tokens: 0,
      output_tokens: 0,
      thinking_tokens: 0,
      total_tokens: 0,
      cost_usd_estimate: '0.000000',
    },
    limits: {
      max_turns: 6,
      max_tool_calls: 8,
      max_clarification_rounds: 2,
      max_total_tokens: 200000,
      max_cost_usd: null,
    },
    project_usage: { cost_usd_estimate: '0.000000', cost_limit_usd: null },
    questions: [],
    draft: null,
    block_refs: [],
    problems: [],
    candidate_version_id: null,
    error: null,
    ...overrides,
  };
}

const EPIC_ID = '019a3a5e-0000-7000-8000-000000000101';
export const STORY_ID = '019a3a5e-0000-7000-8000-000000000102';
export const SOURCED_ID = '019a3a5e-0000-7000-8000-000000000201';
export const CONFIRMED_ID = '019a3a5e-0000-7000-8000-000000000202';
export const PROPOSED_ID = '019a3a5e-0000-7000-8000-000000000203';
export const LENGTH_DECISION_ID = '019a3a5e-0000-7000-8000-000000000301';
export const CANCEL_DECISION_ID = '019a3a5e-0000-7000-8000-000000000302';

const BLOCKERS: Schemas['Blocker'][] = [
  {
    code: 'unresolved_conflict',
    message: 'Sources conflict and the question was skipped: Maximum booking length',
    item_id: STORY_ID,
    decision_id: LENGTH_DECISION_ID,
    criterion_id: null,
  },
  {
    code: 'proposed_criterion',
    message: 'An AI-proposed criterion has not been reviewed',
    item_id: STORY_ID,
    decision_id: null,
    criterion_id: PROPOSED_ID,
  },
];

export const BACKLOG: Schemas['BacklogVersionResponse'] = {
  id: VERSION_ID,
  project_id: PROJECT_ID,
  base_version_id: null,
  revision: 1,
  state: 'draft',
  content_hash: 'b'.repeat(64),
  run_id: RUN_ID,
  source_version_ids: [BRIEF.id, TRANSCRIPT.id],
  items: [
    {
      id: EPIC_ID,
      kind: 'epic',
      parent_id: null,
      title: 'Book a study room',
      description: 'Students and staff book library study rooms themselves.',
      criteria: [],
      assumptions: [],
      open_questions: [],
      blockers: [],
      human_edited: false,
    },
    {
      id: STORY_ID,
      kind: 'story',
      parent_id: EPIC_ID,
      title: 'Search for and book a one-off slot',
      description: 'As a signed-in user, I want to book a one-off slot, so that I can study.',
      criteria: [
        {
          id: SOURCED_ID,
          text: 'A signed-in user can search rooms by date, time and capacity.',
          origin: 'source',
          evidence: [
            {
              source_version_id: BRIEF.id,
              block_id: '019a3a5e-0000-7000-8000-0000000000c2',
              quote: 'search rooms by date, time and capacity',
              relationship: 'supporting',
            },
          ],
          confirmed_by: [],
        },
        {
          id: CONFIRMED_ID,
          text: 'A user can cancel their booking up to one hour before it starts.',
          origin: 'human',
          evidence: [],
          confirmed_by: [CANCEL_DECISION_ID],
        },
        {
          id: PROPOSED_ID,
          text: 'After booking, the user sees a confirmation with the room and time.',
          origin: 'proposed',
          evidence: [],
          confirmed_by: [],
        },
      ],
      assumptions: ['Rooms are the group-study rooms in the library.'],
      open_questions: [],
      blockers: BLOCKERS,
      human_edited: false,
    },
  ],
  decisions: [
    {
      id: LENGTH_DECISION_ID,
      kind: 'conflict',
      status: 'skipped',
      subject: 'Maximum booking length',
      question: 'Is the maximum booking length four hours or three hours?',
      why_it_matters: 'The brief and the transcript disagree.',
      evidence: [FOUR_HOURS, THREE_HOURS],
      affected_item_ids: [STORY_ID],
      question_id: LENGTH_QUESTION.id,
      answer: null,
      decided_by: REVIEWER_ID,
      decided_at: '2026-10-13T10:00:00Z',
    },
    {
      id: CANCEL_DECISION_ID,
      kind: 'missing_decision',
      status: 'answered',
      subject: 'Cancellation and no-shows',
      question: 'How late may a user cancel a booking?',
      why_it_matters: 'The sources leave the cancellation rule open.',
      evidence: [],
      affected_item_ids: [STORY_ID],
      question_id: CANCEL_QUESTION.id,
      answer: CANCEL_ANSWER,
      decided_by: REVIEWER_ID,
      decided_at: '2026-10-13T10:00:00Z',
    },
  ],
  out_of_scope: [
    {
      kind: 'excluded',
      summary: 'Recurring reservations are out of scope for release one.',
      evidence: [
        {
          source_version_id: TRANSCRIPT.id,
          block_id: '019a3a5e-0000-7000-8000-0000000000c4',
          quote: 'Recurring reservations are out of scope for release one.',
          relationship: 'supporting',
        },
      ],
    },
  ],
  blockers: BLOCKERS,
  created_at: '2026-10-13T10:01:00Z',
};

export function errorBody(code: string, message: string, retryable = false) {
  return {
    code,
    message,
    request_id: '019a3a5e-1111-7000-8000-000000000000',
    retryable,
    details: {},
  };
}
