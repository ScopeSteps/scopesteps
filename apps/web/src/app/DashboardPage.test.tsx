import type { components } from '@scopesteps/api-client';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID, REVIEWER_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type Dashboard = components['schemas']['DashboardResponse'];

const PAGE = `/projects/${PROJECT_ID}/dashboard`;
const V1_ID = '019a3a5e-0000-7000-8000-0000000000d1';
const QUESTION_ID = '019a3a5e-0000-7000-8000-0000000000b1';
const STATUSES = [
  'analyzing',
  'in_review',
  'no_change_needed',
  'approved',
  'rejected',
  'failed',
] as const;

function dashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    status: {
      state: 'baseline',
      baseline_version: 2,
      baseline_version_id: VERSION_ID,
      open_version_id: null,
    },
    has_sources: true,
    counts: { version_id: VERSION_ID, approved: true, epics: 3, stories: 12, tasks: 20 },
    coverage: { version_number: 1, confirmed: 10, covered: 9 },
    open_questions: {
      count: 2,
      oldest: [
        {
          id: QUESTION_ID,
          subject: 'How long may a booking last?',
          asked_at: '2026-11-08T09:00:00Z',
          waited_seconds: 3 * 86400,
        },
      ],
    },
    change_requests: {
      total: 3,
      by_status: STATUSES.map((status) => ({
        status,
        count: status === 'in_review' ? 1 : status === 'approved' ? 2 : 0,
      })),
      decided: 2,
      average_seconds_to_decision: 2 * 86400,
    },
    waiting_on: [
      { user_id: REVIEWER_ID, display_name: 'Ana Approver', role: 'approver', waiting: 3 },
    ],
    timeline: [
      {
        version_id: V1_ID,
        number: 1,
        approved_by: REVIEWER_ID,
        approved_by_name: 'Ana Approver',
        approved_at: '2026-11-01T09:00:00Z',
        change_request_number: null,
      },
      {
        version_id: VERSION_ID,
        number: 2,
        approved_by: REVIEWER_ID,
        approved_by_name: 'Ana Approver',
        approved_at: '2026-11-04T09:00:00Z',
        change_request_number: 1,
      },
    ],
    ...overrides,
  };
}

function serve(body: Dashboard) {
  server.use(http.get(`${API}/projects/${PROJECT_ID}/dashboard`, () => HttpResponse.json(body)));
}

function main() {
  return within(screen.getByRole('main'));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

afterEach(() => {
  resetViewport();
});

describe('The dashboard', () => {
  it('is in the project menu', async () => {
    serve(dashboard());
    const router = renderApp(`/projects/${PROJECT_ID}/chat`);

    await userEvent.click(
      await within(screen.getByRole('navigation', { name: 'Project' })).findByRole('link', {
        name: 'Dashboard',
      }),
    );

    expect(router.state.location.pathname).toBe(PAGE);
    expect(await main().findByText('Approved version')).toBeVisible();
  });

  it('shows each figure as a tile that opens the page behind it', async () => {
    serve(dashboard());
    renderApp(PAGE);

    const approved = await main().findByRole('link', { name: /^Approved version v2/ });
    expect(approved).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`,
    );
    expect(approved).toHaveTextContent('by Ana Approver');
    expect(main().getByRole('link', { name: /^Stories 12/ })).toHaveTextContent(
      '3 epics · 20 tasks',
    );
    const coverage = main().getByRole('link', { name: /^Requirements covered 90%/ });
    expect(coverage).toHaveAttribute('href', `/projects/${PROJECT_ID}/backlog?version=${V1_ID}`);
    expect(coverage).toHaveTextContent('9 of 10 confirmed requirements, as drafted for v1');
    expect(within(coverage).getByRole('meter', { name: 'Requirements covered' })).toHaveAttribute(
      'aria-valuetext',
      '9 of 10',
    );
    expect(main().getByRole('link', { name: /^Open questions 2/ })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/chat`,
    );
    expect(main().getByRole('link', { name: /^Open questions/ })).toHaveTextContent(
      'Oldest waiting 3 days',
    );
    expect(main().getByRole('link', { name: /^Change requests 3/ })).toHaveTextContent(
      '1 in review',
    );
    expect(
      main().getByRole('link', { name: /^Average time to a decision 2 days/ }),
    ).toHaveAttribute('href', `/projects/${PROJECT_ID}/changes`);
    await expectNoAccessibilityViolations();
  });

  it('lists who things wait on, the oldest questions and every change request status', async () => {
    serve(dashboard());
    renderApp(PAGE);

    const waiting = within(await main().findByRole('region', { name: 'Who things wait on' }));
    expect(waiting.getByRole('link', { name: /Ana Approver/ })).toHaveTextContent(
      'Approver3 items waiting',
    );
    expect(waiting.getByRole('link')).toHaveAttribute('href', `/projects/${PROJECT_ID}/team`);
    const questions = within(main().getByRole('region', { name: 'Questions waiting longest' }));
    expect(questions.getByRole('link')).toHaveTextContent(
      'How long may a booking last?Waiting 3 days',
    );
    const requests = within(main().getByRole('region', { name: 'Change requests by status' }));
    expect(requests.getAllByRole('link').map((row) => row.textContent)).toEqual([
      'Analyzing…0',
      'In review1',
      'No change needed0',
      'Approved2',
      'Rejected0',
      'Failed0',
    ]);
  });

  it('shows every approved version with who approved it and when, linking to it', async () => {
    serve(dashboard());
    renderApp(PAGE);

    const timeline = within(await main().findByRole('region', { name: 'Approved versions' }));
    const versions = timeline.getAllByRole('listitem');
    expect(versions).toHaveLength(2);
    expect(within(versions[1] ?? document.body).getByRole('link', { name: 'v2' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`,
    );
    expect(versions[1]).toHaveTextContent(/Approved by Ana Approver, .*, from CR-1/);
    expect(versions[0]).not.toHaveTextContent('from CR');
  });

  it('says what to do first on a new project', async () => {
    serve(
      dashboard({
        has_sources: false,
        counts: null,
        coverage: null,
        timeline: [],
        waiting_on: [],
      }),
    );
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Nothing to show yet' })).toBeVisible();
    expect(main().getByRole('link', { name: 'Add a source' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/sources`,
    );
    expect(main().queryByText('Approved version')).not.toBeInTheDocument();
  });

  it('says plainly when nothing is approved, decided or waiting yet', async () => {
    serve(
      dashboard({
        status: {
          state: 'draft_in_progress',
          baseline_version: null,
          baseline_version_id: null,
          open_version_id: VERSION_ID,
        },
        counts: { version_id: VERSION_ID, approved: false, epics: 1, stories: 4, tasks: 0 },
        coverage: { version_number: null, confirmed: 5, covered: 5 },
        open_questions: { count: 0, oldest: [] },
        change_requests: {
          total: 0,
          by_status: STATUSES.map((status) => ({ status, count: 0 })),
          decided: 0,
          average_seconds_to_decision: null,
        },
        waiting_on: [],
        timeline: [],
      }),
    );
    renderApp(PAGE);

    expect(await main().findByRole('link', { name: /^Approved version None yet/ })).toBeVisible();
    expect(main().getByRole('link', { name: /^Stories in the draft 4/ })).toBeVisible();
    expect(main().getByRole('link', { name: /^Requirements covered 100%/ })).toHaveTextContent(
      ', in the draft',
    );
    expect(main().getByText('Nothing waits on anyone right now.')).toBeVisible();
    expect(main().getByText('The agent has no question waiting.')).toBeVisible();
    expect(main().getByText('No change request decided yet')).toBeVisible();
    expect(main().getByText(/once v1 is approved on the Backlog/)).toBeVisible();
  });

  it('offers to try again when the figures cannot load', async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/dashboard`, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(errorBody('INTERNAL', 'Something went wrong.', true), {
              status: 500,
            })
          : HttpResponse.json(dashboard());
      }),
    );
    renderApp(PAGE);

    expect(await main().findByRole('alert')).toHaveTextContent(
      'Could not load the dashboard. Something went wrong.',
    );
    await userEvent.click(main().getByRole('button', { name: 'Try again' }));

    expect(await main().findByText('Approved version')).toBeVisible();
  });

  it('works at phone width', async () => {
    setNarrowViewport(true);
    serve(dashboard());
    renderApp(PAGE);

    expect(await main().findByText('Approved version')).toBeVisible();
    await expectNoAccessibilityViolations();
  });
});
