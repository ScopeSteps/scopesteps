import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  APPROVER,
  BACKLOG,
  EPIC_ID,
  errorBody,
  makeReview,
  PERMISSIONS,
  PROJECT,
  PROJECT_ID,
  REVIEWER_ID,
  STORY_ID,
  VERSION_ID,
  versionSummary,
  VIEWER,
} from '@/test/fixtures';
import { API, JIRA_URL, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import {
  jiraConnection,
  jiraPublish,
  jiraStatus,
  kindCounts,
  PUBLISH_ID,
} from '@/test/jiraFixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const TASK_ID = '019a3a5e-0000-7000-8000-0000000001a1';
const READY = {
  ...BACKLOG,
  blockers: [],
  items: BACKLOG.items.map((item) => ({
    ...item,
    blockers: [],
    tasks:
      item.id === STORY_ID
        ? [
            {
              id: TASK_ID,
              title: 'Check overlapping bookings',
              origin: 'person' as const,
              suggestion: null,
              edited_by: REVIEWER_ID,
              flag: null,
            },
          ]
        : [],
  })),
};
const APPROVED = { ...READY, state: 'approved' as const };
const STORY_TITLE = 'Search for and book a one-off slot';

function asApprover(status: 'baseline' | 'draft') {
  return [
    http.get(`${API}/me`, () => HttpResponse.json(APPROVER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        role: 'approver',
        permissions: PERMISSIONS.approver,
        status:
          status === 'baseline'
            ? {
                state: 'baseline',
                baseline_version: 1,
                baseline_version_id: VERSION_ID,
                open_version_id: null,
              }
            : { ...PROJECT.status, state: 'draft_in_progress', open_version_id: VERSION_ID },
      }),
    ),
    http.get(VERSIONS_URL, () =>
      HttpResponse.json({
        versions: status === 'baseline' ? [versionSummary(VERSION_ID, { number: 1 })] : [],
        next_cursor: null,
      }),
    ),
  ];
}

interface Started {
  key: string | null;
  body: unknown;
}

/** Approved v1 with Jira connected; publishes answer from `publishes`, which tests change. */
function serveApprovedWithJira({
  status = jiraStatus(jiraConnection()),
  start = () => jiraPublish(),
}: {
  status?: ReturnType<typeof jiraStatus>;
  start?: () => ReturnType<typeof jiraPublish>;
} = {}) {
  const state = { publishes: [] as ReturnType<typeof jiraPublish>[], starts: [] as Started[] };
  const retries: string[] = [];
  server.use(
    ...asApprover('baseline'),
    http.get(`${VERSIONS_URL}/${VERSION_ID}`, () => HttpResponse.json(APPROVED)),
    http.get(`${JIRA_URL}/connection`, () => HttpResponse.json(status)),
    http.get(`${JIRA_URL}/preview`, ({ request }) =>
      HttpResponse.json({
        version_id: new URL(request.url).searchParams.get('version_id') ?? '',
        jira_project_key: 'WEB',
        counts: kindCounts([1, 1, 1]),
      }),
    ),
    http.get(`${JIRA_URL}/publishes`, () => HttpResponse.json({ publishes: state.publishes })),
    http.post(`${JIRA_URL}/publishes`, async ({ request }) => {
      state.starts.push({
        key: request.headers.get('Idempotency-Key'),
        body: await request.json(),
      });
      await delay(30);
      const publish = start();
      state.publishes = [publish];
      return HttpResponse.json(publish, { status: 201 });
    }),
    http.post(`${API}/jira/publishes/:id/retry`, ({ params }) => {
      retries.push(String(params.id));
      const publish = jiraPublish({ status: 'sending', sent: 2, total: 3 });
      state.publishes = [publish];
      return HttpResponse.json(publish);
    }),
  );
  return { state, retries };
}

function main() {
  return within(screen.getByRole('main'));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Publishing an approved version to Jira', () => {
  it('previews the counts, publishes once on confirm, then shows progress and the result', async () => {
    const { state } = serveApprovedWithJira();
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'Publish to Jira…' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Publish v1 to Jira' }));
    const table = within(await dialog.findByRole('table'));
    expect(table.getByRole('columnheader', { name: 'In Jira project WEB' })).toBeVisible();
    const create = within(table.getByRole('row', { name: /^Create/ }));
    expect(create.getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['1', '1', '1']);
    expect(dialog.getByText(/Nothing is sent until you confirm/)).toBeVisible();
    expect(state.starts).toHaveLength(0);
    await expectNoAccessibilityViolations();

    const confirm = dialog.getByRole('button', { name: 'Publish to Jira' });
    await userEvent.dblClick(confirm);

    expect(
      await screen.findByText('Publishing v1 to Jira. It keeps going if you leave the page.'),
    ).toBeVisible();
    expect(state.starts).toEqual([
      { key: expect.any(String) as string, body: { version_id: VERSION_ID } },
    ]);
    expect(await main().findByText(/Publishing to Jira: 0 of 3 sent/)).toBeVisible();

    state.publishes = [
      jiraPublish({ status: 'done', sent: 3, finished_at: '2026-11-11T09:01:00Z' }),
    ];
    expect(
      await main().findByText(/Published to Jira .*: 3 created\./, undefined, { timeout: 4000 }),
    ).toBeVisible();
  });

  it('lists the items that failed and retries only those', async () => {
    const { state, retries } = serveApprovedWithJira();
    state.publishes = [
      jiraPublish({
        status: 'failed',
        sent: 2,
        finished_at: '2026-11-11T09:01:00Z',
        failed: [
          { item_id: TASK_ID, kind: 'task', operation: 'create', error_code: 'JIRA_REJECTED' },
        ],
      }),
    ];
    renderApp(PAGE);

    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent('1 item did not reach Jira.');
    expect(
      within(alert).getByRole('list', { name: 'Items that did not reach Jira' }),
    ).toHaveTextContent(
      'Task “Check overlapping bookings”: could not create it, because Jira refused its fields.',
    );

    await userEvent.click(within(alert).getByRole('button', { name: 'Retry failed items' }));

    expect(retries).toEqual([PUBLISH_ID]);
    expect(await main().findByText(/Publishing to Jira: 2 of 3 sent/)).toBeVisible();
  });

  it('says why a whole publish stopped', async () => {
    const { state } = serveApprovedWithJira();
    state.publishes = [
      jiraPublish({ status: 'failed', sent: 1, last_error: 'JIRA_FORBIDDEN', failed: [] }),
    ];
    renderApp(PAGE);

    expect(await main().findByRole('alert')).toHaveTextContent(
      'Publishing to Jira stopped. The Jira account may not create issues in that project. 1 of 3 were sent.',
    );
  });

  it('shows the server’s reason when publishing cannot start', async () => {
    serveApprovedWithJira();
    server.use(
      http.post(`${JIRA_URL}/publishes`, () =>
        HttpResponse.json(errorBody('PUBLISH_IN_PROGRESS', 'Another publish is still sending.'), {
          status: 409,
        }),
      ),
    );
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'Publish to Jira…' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Publish v1 to Jira' }));
    await dialog.findByRole('table');
    await userEvent.click(dialog.getByRole('button', { name: 'Publish to Jira' }));

    expect(await dialog.findByRole('alert')).toHaveTextContent(
      'Nothing was published. Another publish is still sending.',
    );
  });

  it('keeps the button but disables it while the token needs renewing', async () => {
    serveApprovedWithJira({
      status: jiraStatus(
        jiraConnection({ token_state: 'expired', token_expires_on: '2026-11-01' }),
      ),
    });
    renderApp(PAGE);

    const button = await main().findByRole('button', { name: 'Publish to Jira…' });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription('The Jira token needs renewing in Project settings');
  });

  it('offers nothing to someone who may not publish, or when Jira is not connected', async () => {
    serveApprovedWithJira({ status: jiraStatus(null) });
    renderApp(PAGE);

    expect(await main().findByRole('button', { name: 'Export' })).toBeVisible();
    expect(main().queryByRole('button', { name: 'Publish to Jira…' })).not.toBeInTheDocument();
  });
});

describe('Jira keys on items', () => {
  it('links each published epic, story and task to its Jira issue, for any member', async () => {
    serveApprovedWithJira({
      status: jiraStatus(jiraConnection({ email: null }), { canManage: false, canPublish: false }),
    });
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${JIRA_URL}/issues`, () =>
        HttpResponse.json({
          issues: [
            {
              item_id: EPIC_ID,
              kind: 'epic',
              jira_key: 'WEB-1',
              url: 'https://example-team.atlassian.net/browse/WEB-1',
              closed: false,
            },
            {
              item_id: STORY_ID,
              kind: 'story',
              jira_key: 'WEB-2',
              url: 'https://example-team.atlassian.net/browse/WEB-2',
              closed: false,
            },
            { item_id: TASK_ID, kind: 'task', jira_key: 'WEB-3', url: null, closed: true },
          ],
        }),
      ),
    );
    renderApp(PAGE);

    expect(await main().findByRole('link', { name: 'Open WEB-1 in Jira' })).toHaveAttribute(
      'href',
      'https://example-team.atlassian.net/browse/WEB-1',
    );
    expect(main().getByRole('link', { name: 'Open WEB-2 in Jira' })).toHaveAttribute(
      'target',
      '_blank',
    );
    await userEvent.click(
      main().getByRole('button', { name: new RegExp(`^Story ${STORY_TITLE}`) }),
    );
    expect(await main().findByText('WEB-3 (closed in Jira)')).toBeVisible();
    expect(main().queryByRole('link', { name: /WEB-3/ })).not.toBeInTheDocument();
  });
});

describe('Also publishing from the approve window', () => {
  function serveDraft({ status = jiraStatus(jiraConnection()), decision = {} } = {}) {
    const approvals: unknown[] = [];
    server.use(
      ...asApprover('draft'),
      http.get(`${VERSIONS_URL}/${VERSION_ID}`, () => HttpResponse.json(READY)),
      http.get(`${JIRA_URL}/connection`, () => HttpResponse.json(status)),
      http.get(`${JIRA_URL}/publishes`, () => HttpResponse.json({ publishes: [] })),
      http.post(`${API}/backlogs/${VERSION_ID}/review`, () => HttpResponse.json(makeReview())),
      http.post(`${API}/backlogs/${VERSION_ID}/approve`, async ({ request }) => {
        approvals.push(await request.json());
        return HttpResponse.json({
          id: '019a3a5e-0000-7000-8000-000000000401',
          version_id: VERSION_ID,
          decision: 'approved',
          decided_by: REVIEWER_ID,
          revision: 1,
          content_hash: BACKLOG.content_hash,
          decided_at: '2026-11-11T12:00:00Z',
          baseline_version: 1,
          current_baseline_id: VERSION_ID,
          jira_publish_id: null,
          jira_problem: null,
          ...decision,
        });
      }),
    );
    return approvals;
  }

  async function openApprove() {
    await userEvent.click(await main().findByRole('button', { name: 'Approve as v1…' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Approve as v1' }));
    await dialog.findByRole('list', { name: 'Approval checks' });
    return dialog;
  }

  it('is unchecked by default and sends the choice with the approval', async () => {
    const approvals = serveDraft({ decision: { jira_publish_id: PUBLISH_ID } });
    renderApp(PAGE);

    const dialog = await openApprove();
    const box = dialog.getByRole('checkbox', { name: /Also publish to Jira/ });
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));

    expect(
      await screen.findByText(
        'Approved v1 saved. It can’t be overwritten. Publishing to Jira has started.',
      ),
    ).toBeVisible();
    expect(approvals).toEqual([expect.objectContaining({ also_publish_to_jira: true })]);
  });

  it('is not offered when the project has no Jira connection', async () => {
    serveDraft({ status: jiraStatus(null) });
    renderApp(PAGE);

    const dialog = await openApprove();
    expect(dialog.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('says so when the approval is saved but the publish could not start', async () => {
    serveDraft({ decision: { jira_problem: 'JIRA_TOKEN_EXPIRED' } });
    renderApp(PAGE);

    const dialog = await openApprove();
    await userEvent.click(dialog.getByRole('checkbox', { name: /Also publish to Jira/ }));
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(
      await main().findByText(/The version was approved, but publishing to Jira did not start/),
    ).toHaveTextContent('The Jira API token expired.');
  });
});
