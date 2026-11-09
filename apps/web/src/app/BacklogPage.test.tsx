import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { BACKLOG, CANCEL_QUESTION, makeRun, PROJECT_ID, RUN_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const PAGE = `/projects/${PROJECT_ID}/backlog`;
const CHAT = `/projects/${PROJECT_ID}/chat`;

function main() {
  return within(screen.getByRole('main'));
}

function serveRun(
  run = makeRun({ status: 'ready_for_review', revision: 9, candidate_version_id: VERSION_ID }),
) {
  server.use(http.get(`${API}/runs/${RUN_ID}`, () => HttpResponse.json(run)));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    ...projectHandlers(),
    http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
      HttpResponse.json(BACKLOG),
    ),
  );
  serveRun();
});

describe('BacklogPage', () => {
  it('points back to the chat when no run or version is known', async () => {
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'No backlog yet' })).toBeVisible();
    expect(main().getByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', CHAT);
  });

  it('restores a finished run and its saved candidate from the run id in the URL', async () => {
    renderApp(`${PAGE}?run=${RUN_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
    expect(main().getByRole('heading', { level: 4, name: 'Epic Book a study room' })).toBeVisible();
  });

  it('shows a backlog version by its id alone, even when its run cannot be loaded', async () => {
    server.use(
      http.get(`${API}/runs/${RUN_ID}`, () =>
        HttpResponse.json({ code: 'NOT_FOUND', message: 'Run not found' }, { status: 404 }),
      ),
    );
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
    expect(main().queryByRole('heading', { name: /Requirements covered/ })).toBeNull();
  });

  it('shows the draft of the last run started in this browser', async () => {
    window.localStorage.setItem(`scopesteps:last-run:${PROJECT_ID}`, RUN_ID);

    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
  });

  it('sends the reviewer to the questions while the run waits for answers', async () => {
    serveRun(makeRun({ status: 'waiting_for_input', questions: [CANCEL_QUESTION] }));

    renderApp(`${PAGE}?run=${RUN_ID}`);

    expect(await main().findByRole('heading', { name: 'Your backlog appears here' })).toBeVisible();
    expect(main().getByRole('link', { name: 'Go to the questions' })).toHaveAttribute(
      'href',
      `${CHAT}?run=${RUN_ID}`,
    );
  });
});

const LENGTH_BLOCK = '019a3a5e-0000-7000-8000-0000000000c2';

function coveredRun(uncovered: number) {
  const statements = Array.from({ length: 3 }, (_, index) => ({
    id: `C${String(index + 1)}`,
    kind: 'confirmed' as const,
    summary: `Confirmed requirement ${String(index + 1)}`,
    citations: [{ block_id: 'B1', quote: 'A booking can last up to 4 hours.' }],
  }));
  return makeRun({
    status: 'ready_for_review',
    candidate_version_id: VERSION_ID,
    draft: { items: [], questions: [], people: [], statements },
    block_refs: [{ label: 'B1', source_block_id: LENGTH_BLOCK, question_id: null }],
    coverage: {
      confirmed: 3,
      covered: 3 - uncovered,
      uncovered: statements.slice(3 - uncovered).map((statement) => ({
        statement_id: statement.id,
        summary: statement.summary,
        citations: statement.citations,
      })),
    },
  });
}

describe('BacklogPage coverage', () => {
  it('counts the covered requirements and lists the uncovered ones with their quotes', async () => {
    serveRun(coveredRun(1));
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    expect(
      await main().findByRole('heading', { name: 'Requirements covered: 2 of 3' }),
    ).toBeVisible();
    const missing = main().getByRole('list', { name: 'Not covered by a story' });
    expect(within(missing).getByText('Confirmed requirement 3')).toBeVisible();

    await userEvent.click(
      within(missing).getByRole('button', {
        name: 'Show the quote for “Confirmed requirement 3”',
      }),
    );

    const sheet = await screen.findByRole('dialog', { name: 'Evidence' });
    expect(within(sheet).getByText('Confirmed requirement 3')).toBeVisible();
    expect(await within(sheet).findByText(/A booking can last up to 4 hours/)).toBeVisible();
  });

  it('says every requirement has a story when nothing is missing', async () => {
    serveRun(coveredRun(0));
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    expect(
      await main().findByRole('heading', { name: 'Requirements covered: 3 of 3' }),
    ).toBeVisible();
    expect(main().getByText(/Every one of the 3 confirmed requirements has a story/)).toBeVisible();
    expect(main().queryByRole('list', { name: 'Not covered by a story' })).toBeNull();
  });

  it('hides and shows the uncovered list', async () => {
    serveRun(coveredRun(2));
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    const toggle = await main().findByRole('button', { name: /the 2 not covered/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(main().queryByRole('list', { name: 'Not covered by a story' })).toBeNull();
  });

  it('shows no coverage for a version a change request proposed', async () => {
    serveRun({ ...coveredRun(1), mode: 'change' });
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
    expect(main().queryByRole('heading', { name: /Requirements covered/ })).toBeNull();
  });
});

describe('BacklogPage drafting progress', () => {
  it.each([
    [{ outline_written: false, epics: 0, epics_written: 0 }, 'Writing the outline of epics…'],
    [{ outline_written: true, epics: 7, epics_written: 2 }, 'Writing epic 3 of 7…'],
    [{ outline_written: true, epics: 7, epics_written: 7 }, 'Putting the backlog together…'],
  ])('shows where a draft written in steps has got', async (drafting, text) => {
    serveRun(makeRun({ status: 'running', stage: 'draft', drafting }));

    renderApp(`${PAGE}?run=${RUN_ID}`);

    expect(await main().findByRole('heading', { name: 'Your backlog appears here' })).toBeVisible();
    expect(main().getByRole('status')).toHaveTextContent(text);
  });
});
