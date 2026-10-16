import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { BACKLOG, CANCEL_QUESTION, makeRun, PROJECT_ID, RUN_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const PAGE = `/projects/${PROJECT_ID}/backlog`;
const CHAT = `/projects/${PROJECT_ID}/chat`;
let runRequests = 0;

function main() {
  return within(screen.getByRole('main'));
}

function serveRun(
  run = makeRun({ status: 'ready_for_review', revision: 9, candidate_version_id: VERSION_ID }),
) {
  server.use(
    http.get(`${API}/runs/${RUN_ID}`, () => {
      runRequests += 1;
      return HttpResponse.json(run);
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  runRequests = 0;
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

  it('shows a backlog version by its id alone', async () => {
    renderApp(`${PAGE}?version=${VERSION_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
    expect(runRequests).toBe(0);
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
