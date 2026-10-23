import { focusManager } from '@tanstack/react-query';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { BACKLOG, PROJECT_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const STORY = 'Search for and book a one-off slot';
const SUBJECT = 'Maximum booking length';

function main() {
  return within(screen.getByRole('main'));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('An open answer form while the backlog refreshes', () => {
  it.each([
    ['in a story’s blockers', () => main().getByRole('list', { name: `Blockers for ${STORY}` })],
    ['in the decisions list', () => main().getByRole('list', { name: 'Decisions' })],
  ])('keeps its text %s when the version is read again', async (_, place) => {
    let reads = 0;
    server.use(
      http.get(BACKLOG_URL, () => {
        reads += 1;
        return HttpResponse.json(reads === 1 ? BACKLOG : { ...BACKLOG, revision: 2 });
      }),
    );
    renderApp(PAGE);

    await main().findByRole('list', { name: `Blockers for ${STORY}` });
    const where = within(place());
    await userEvent.click(where.getByRole('button', { name: `Answer: ${SUBJECT}` }));
    await userEvent.type(
      within(where.getByRole('form', { name: `Answer: ${SUBJECT}` })).getByRole('textbox', {
        name: 'Your answer',
      }),
      'Three hours.',
    );

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => {
      expect(reads).toBe(2);
    });

    const form = within(within(place()).getByRole('form', { name: `Answer: ${SUBJECT}` }));
    expect(form.getByRole('textbox', { name: 'Your answer' })).toHaveValue('Three hours.');
    focusManager.setFocused(undefined);
  });
});
