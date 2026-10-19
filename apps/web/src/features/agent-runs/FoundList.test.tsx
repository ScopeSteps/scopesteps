import type { components } from '@scopesteps/api-client';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BRIEF, makeRun, PROJECT_ID, RUN_ID, TRANSCRIPT } from '@/test/fixtures';
import { API, MESSAGES_URL, projectHandlers, SOURCES_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Message, Statement } from './types';

type SourceBlock = components['schemas']['SourceBlockResponse'];
type SourceVersion = components['schemas']['SourceVersionResponse'];

const CHAT = `/projects/${PROJECT_ID}/chat`;
const PARAGRAPHS = 6;
const CONTEXT =
  'Background, attendees and the booking rules the brief and the meeting agree on for release one.';
const DECISION = 'A booking can last up to three hours.';

function blocks(source: SourceVersion, idPrefix: string): SourceBlock[] {
  return Array.from({ length: PARAGRAPHS }, (_, index) => ({
    id: `019a3a5e-0000-7000-8000-${idPrefix}${String(index + 1).padStart(4, '0')}`,
    source_version_id: source.id,
    source_kind: source.kind,
    ordinal: index + 1,
    text: `Paragraph ${String(index + 1)} of the ${source.kind}.`,
    locator: { paragraph: index + 1, start_offset: 0, end_offset: 30 },
  }));
}

const BRIEF_PARAGRAPHS = blocks(BRIEF, '00000001');
const TRANSCRIPT_PARAGRAPHS = blocks(TRANSCRIPT, '00000002');
const CITED = [...BRIEF_PARAGRAPHS, ...TRANSCRIPT_PARAGRAPHS];

const STATEMENTS: Statement[] = [
  {
    id: 'T1',
    kind: 'confirmed',
    summary: DECISION,
    citations: [{ block_id: 'B1', quote: 'Paragraph 1 of the brief.' }],
  },
  {
    id: 'T2',
    kind: 'context',
    summary: CONTEXT,
    citations: CITED.map((block, index) => ({
      block_id: `B${String(index + 1)}`,
      quote: block.text,
    })),
  },
];

const RUN = makeRun({
  status: 'ready_for_review',
  stage: 'draft',
  draft: { items: [], questions: [], statements: STATEMENTS },
  block_refs: CITED.map((block, index) => ({
    label: `B${String(index + 1)}`,
    source_block_id: block.id,
    question_id: null,
  })),
});

const READY: Message = {
  id: '019a3a5e-0000-7000-8000-000000000e01',
  author: null,
  claims: [],
  created_at: '2026-10-19T09:00:00Z',
  event: 'run.ready_for_review',
  change_request_id: null,
  baseline_version: null,
  kind: 'event',
  question: null,
  question_id: null,
  role: 'system',
  run_id: RUN_ID,
  text: 'Draft ready for review',
};

function finding(summary: string) {
  const list = screen.getByRole('list', { name: 'What the agent found' });
  const row = within(list)
    .getAllByRole('listitem')
    .find((item) => within(item).queryByText(summary));
  if (!row) throw new Error(`No finding reads “${summary}”`);
  return within(row);
}

beforeEach(() => {
  server.use(...projectHandlers());
  server.use(
    http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () => HttpResponse.json(BRIEF_PARAGRAPHS)),
    http.get(`${SOURCES_URL}/${TRANSCRIPT.id}/blocks`, () =>
      HttpResponse.json(TRANSCRIPT_PARAGRAPHS),
    ),
    http.get(MESSAGES_URL, () =>
      HttpResponse.json({ messages: [READY], next_cursor: null, active_run: null }),
    ),
    http.get(`${API}/runs/${RUN_ID}`, () => HttpResponse.json(RUN)),
  );
});

describe('What the agent found', () => {
  // jsdom has no layout, so how wide the summary stays is checked in a browser, not here.
  it('keeps every citation of a statement that cites many paragraphs, in order, in its row', async () => {
    renderApp(CHAT);

    expect(
      await screen.findByRole('button', { name: `Transcript ¶6, evidence for: ${CONTEXT}` }),
    ).toBeVisible();
    const context = finding(CONTEXT);
    expect(context.getByText('Context')).toBeVisible();
    expect(context.getAllByRole('button').map((chip) => chip.textContent)).toEqual([
      ...BRIEF_PARAGRAPHS.map((block) => `Brief ¶${String(block.ordinal)}`),
      ...TRANSCRIPT_PARAGRAPHS.map((block) => `Transcript ¶${String(block.ordinal)}`),
    ]);
    expect(
      finding(DECISION)
        .getAllByRole('button')
        .map((chip) => chip.textContent),
    ).toEqual(['Brief ¶1']);
    await expectNoAccessibilityViolations();
  });

  it('opens the paragraph a late citation points at', async () => {
    const user = userEvent.setup();
    renderApp(CHAT);

    await user.click(
      await screen.findByRole('button', { name: `Transcript ¶5, evidence for: ${CONTEXT}` }),
    );

    expect(
      await within(screen.getByRole('dialog')).findByText('Paragraph 5 of the transcript.', {
        exact: false,
      }),
    ).toBeVisible();
  });
});
