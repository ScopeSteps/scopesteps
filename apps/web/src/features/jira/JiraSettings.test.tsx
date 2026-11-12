import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { ToastProvider } from '@/components/ToastProvider';
import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID } from '@/test/fixtures';
import { JIRA_URL } from '@/test/handlers';
import { jiraConnection, jiraStatus } from '@/test/jiraFixtures';
import { server } from '@/test/server';

import { JiraSettings } from './JiraSettings';

type Status = ReturnType<typeof jiraStatus>;

function renderSettings() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <JiraSettings projectId={PROJECT_ID} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return within(screen.getByRole('region', { name: 'Jira' }));
}

interface Sent {
  method: string;
  body: unknown;
}

/** The connection endpoints, answering from `status` and recording what was sent. */
function serveJira(initial: Status, replies: Partial<Record<string, () => Response>> = {}) {
  let status = initial;
  const sent: Sent[] = [];
  const record = async (method: string, request: Request) => {
    const text = await request.text();
    sent.push({ method, body: text ? (JSON.parse(text) as unknown) : null });
  };
  server.use(
    http.get(`${JIRA_URL}/connection`, () => HttpResponse.json(status)),
    http.put(`${JIRA_URL}/connection`, async ({ request }) => {
      await record('PUT', request);
      const reply = replies.PUT?.();
      if (reply) {
        return reply;
      }
      const connection = jiraConnection({ token_expires_on: '2027-03-01' });
      status = jiraStatus(connection);
      return HttpResponse.json(connection);
    }),
    http.patch(`${JIRA_URL}/connection`, async ({ request }) => {
      await record('PATCH', request);
      const reply = replies.PATCH?.();
      if (reply) {
        return reply;
      }
      const current = status.connection ?? jiraConnection();
      const connection = { ...current, auto_publish: true, revision: current.revision + 1 };
      status = { ...status, connection };
      return HttpResponse.json(connection);
    }),
    http.post(`${JIRA_URL}/connection/test`, async ({ request }) => {
      await record('TEST', request);
      return replies.TEST?.() ?? HttpResponse.json(status.connection);
    }),
    http.delete(`${JIRA_URL}/connection`, async ({ request }) => {
      await record('DELETE', request);
      status = jiraStatus(null);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return sent;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('Connecting Jira', () => {
  it('lets an approver connect with the token, explains the separate account and never keeps the token', async () => {
    const sent = serveJira(jiraStatus(null));
    const section = renderSettings();

    await userEvent.click(await section.findByRole('button', { name: 'Connect Jira' }));
    const form = within(section.getByRole('form', { name: 'Connect Jira' }));
    expect(form.getByText(/Use a separate Jira account/)).toBeVisible();
    expect(form.getByRole('link', { name: 'How to set it up' })).toHaveAttribute(
      'href',
      expect.stringContaining('docs/product/jira-setup.md') as string,
    );
    await expectNoAccessibilityViolations();

    await userEvent.type(form.getByLabelText('Jira address'), 'example-team.atlassian.net');
    await userEvent.type(form.getByLabelText('Jira account email'), 'scopesteps-bot@example.test');
    await userEvent.type(form.getByLabelText('API token'), 'synthetic-token-value');
    await userEvent.type(form.getByLabelText('Jira project key'), 'web');
    await userEvent.type(form.getByLabelText('Token expires on (optional)'), '2027-03-01');
    await userEvent.click(form.getByRole('button', { name: 'Connect' }));

    expect(await screen.findByText('Jira connected. The details worked.')).toBeVisible();
    expect(sent).toEqual([
      {
        method: 'PUT',
        body: {
          site_url: 'example-team.atlassian.net',
          email: 'scopesteps-bot@example.test',
          api_token: 'synthetic-token-value',
          project_key: 'WEB',
          token_expires_on: '2027-03-01',
        },
      },
    ]);
    expect(await section.findByText('Connected as')).toBeVisible();
    expect(section.getByText('ScopeSteps Bot')).toBeVisible();
    expect(section.getByRole('link', { name: 'Website' })).toHaveAttribute(
      'href',
      'https://example-team.atlassian.net/browse/WEB',
    );
    expect(section.getByText('Mar 1, 2027')).toBeVisible();
    expect(screen.queryByDisplayValue('synthetic-token-value')).not.toBeInTheDocument();
  });

  it('names each missing field and sends nothing', async () => {
    const sent = serveJira(jiraStatus(null));
    const section = renderSettings();

    await userEvent.click(await section.findByRole('button', { name: 'Connect Jira' }));
    await userEvent.click(section.getByRole('button', { name: 'Connect' }));

    expect(section.getByText('Enter your Jira address.')).toBeVisible();
    expect(section.getByText('Paste an API token of that account.')).toBeVisible();
    expect(section.getByLabelText('Jira project key')).toHaveAttribute('aria-invalid', 'true');
    expect(sent).toHaveLength(0);
  });

  it('shows what Jira refused and keeps the form open', async () => {
    serveJira(jiraStatus(null), {
      PUT: () =>
        HttpResponse.json(
          errorBody('JIRA_AUTH_FAILED', 'Jira did not accept that email and API token.'),
          { status: 422 },
        ),
    });
    const section = renderSettings();

    await userEvent.click(await section.findByRole('button', { name: 'Connect Jira' }));
    await userEvent.type(section.getByLabelText('Jira address'), 'example-team.atlassian.net');
    await userEvent.type(section.getByLabelText('Jira account email'), 'bot@example.test');
    await userEvent.type(section.getByLabelText('API token'), 'wrong');
    await userEvent.type(section.getByLabelText('Jira project key'), 'WEB');
    await userEvent.click(section.getByRole('button', { name: 'Connect' }));

    expect(await section.findByRole('alert')).toHaveTextContent(
      'Jira was not connected. Jira did not accept that email and API token.',
    );
    expect(section.getByRole('form', { name: 'Connect Jira' })).toBeVisible();
  });

  it('says so when the server cannot connect to Jira at all', async () => {
    serveJira(jiraStatus(null, { configured: false }));
    const section = renderSettings();

    expect(
      await section.findByText('This ScopeSteps server is not set up to connect to Jira yet.'),
    ).toBeVisible();
    expect(section.queryByRole('button', { name: 'Connect Jira' })).not.toBeInTheDocument();
  });
});

describe('Managing a connection', () => {
  it('turns automatic publishing on with the revision it was shown', async () => {
    const sent = serveJira(jiraStatus(jiraConnection()));
    const section = renderSettings();

    const auto = await section.findByRole('checkbox', {
      name: /Publish approved versions to Jira automatically/,
    });
    expect(auto).not.toBeChecked();
    await userEvent.click(auto);

    await waitFor(() => {
      expect(auto).toBeChecked();
    });
    expect(sent).toEqual([
      { method: 'PATCH', body: { auto_publish: true, publishers: null, expected_revision: 3 } },
    ]);
  });

  it('lets editors publish too when the approver chooses it', async () => {
    const sent = serveJira(jiraStatus(jiraConnection()));
    const section = renderSettings();

    await userEvent.selectOptions(
      await section.findByLabelText('Who can publish to Jira'),
      'Approvers and Editors',
    );

    await waitFor(() => {
      expect(sent).toEqual([
        {
          method: 'PATCH',
          body: { auto_publish: null, publishers: 'approvers_and_editors', expected_revision: 3 },
        },
      ]);
    });
  });

  it('says someone else changed the settings when the revision is stale', async () => {
    serveJira(jiraStatus(jiraConnection()), {
      PATCH: () =>
        HttpResponse.json(errorBody('CONNECTION_CHANGED', 'Someone changed it.'), { status: 409 }),
    });
    const section = renderSettings();

    await userEvent.click(
      await section.findByRole('checkbox', { name: /Publish approved versions/ }),
    );

    expect(await section.findByRole('alert')).toHaveTextContent(
      'Someone else changed the Jira settings meanwhile.',
    );
  });

  it('tests the saved details and reports a failure', async () => {
    const sent = serveJira(jiraStatus(jiraConnection()), {
      TEST: () =>
        HttpResponse.json(errorBody('JIRA_AUTH_FAILED', 'Jira refused the API token.'), {
          status: 422,
        }),
    });
    const section = renderSettings();

    await userEvent.click(await section.findByRole('button', { name: 'Test connection' }));

    expect(await section.findByRole('alert')).toHaveTextContent(
      'The connection test failed. Jira refused the API token.',
    );
    expect(sent.map((each) => each.method)).toEqual(['TEST']);
  });

  it('disconnects only after confirming', async () => {
    const sent = serveJira(jiraStatus(jiraConnection()));
    const section = renderSettings();

    await userEvent.click(await section.findByRole('button', { name: 'Disconnect' }));
    expect(section.getByRole('alert')).toHaveTextContent('Issues already in Jira stay there.');
    expect(sent).toHaveLength(0);
    await userEvent.click(section.getByRole('button', { name: 'Yes, disconnect' }));

    expect(await screen.findByText('Jira disconnected. Its issues stay in Jira.')).toBeVisible();
    expect(sent.map((each) => each.method)).toEqual(['DELETE']);
    expect(await section.findByRole('button', { name: 'Connect Jira' })).toBeVisible();
  });

  it('shows a member what is connected without any controls', async () => {
    serveJira(jiraStatus(jiraConnection({ email: null }), { canManage: false, canPublish: false }));
    const section = renderSettings();

    expect(await section.findByText('ScopeSteps Bot')).toBeVisible();
    expect(section.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(section.queryByRole('button')).not.toBeInTheDocument();
  });

  it('tells a member nobody connected Jira yet', async () => {
    serveJira(jiraStatus(null, { canManage: false }));
    const section = renderSettings();

    expect(await section.findByText('Not connected. An Approver can connect Jira.')).toBeVisible();
  });
});

describe('The token’s state', () => {
  it('warns 14 days or less before the token expires, with Reconnect', async () => {
    serveJira(
      jiraStatus(
        jiraConnection({
          token_state: 'expires_soon',
          token_expires_on: '2026-11-20',
          token_days_left: 9,
        }),
      ),
    );
    const section = renderSettings();

    await section.findByText('ScopeSteps Bot');
    const warning = section.getByRole('status');
    expect(warning).toHaveTextContent(
      'The Jira API token expires in 9 days (Nov 20, 2026). Make a new token and reconnect before then',
    );
    expect(within(warning).getByRole('button', { name: 'Reconnect' })).toBeVisible();
  });

  it('says an expired token stopped publishing, and Reconnect opens the form filled in', async () => {
    serveJira(
      jiraStatus(
        jiraConnection({
          token_state: 'expired',
          token_expires_on: '2026-11-01',
          token_days_left: -10,
        }),
      ),
    );
    const section = renderSettings();

    const alert = await section.findByRole('alert');
    expect(alert).toHaveTextContent(
      'The Jira API token expired on Nov 1, 2026, so publishing to Jira is stopped.',
    );
    await userEvent.click(within(alert).getByRole('button', { name: 'Reconnect' }));

    const form = within(section.getByRole('form', { name: 'Reconnect Jira' }));
    expect(form.getByLabelText('Jira address')).toHaveValue('https://example-team.atlassian.net');
    expect(form.getByLabelText('Jira project key')).toHaveValue('WEB');
    expect(form.getByLabelText('API token')).toHaveValue('');
  });

  it('says plainly when Jira refused the token', async () => {
    serveJira(
      jiraStatus(
        jiraConnection({ token_state: 'rejected', token_rejected_at: '2026-11-10T03:00:00Z' }),
      ),
    );
    const section = renderSettings();

    const alert = await section.findByRole('alert');
    expect(alert).toHaveTextContent('Jira no longer accepts the API token');
    expect(within(alert).getByRole('button', { name: 'Reconnect' })).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('asks a member to get an approver to reconnect', async () => {
    serveJira(
      jiraStatus(jiraConnection({ token_state: 'rejected', email: null }), {
        canManage: false,
        canPublish: false,
      }),
    );
    const section = renderSettings();

    const alert = await section.findByRole('alert');
    expect(alert).toHaveTextContent('Ask an Approver to reconnect.');
    expect(within(alert).queryByRole('button')).not.toBeInTheDocument();
  });

  it('says nothing about a working token', async () => {
    serveJira(jiraStatus(jiraConnection()));
    const section = renderSettings();

    expect(await section.findByText('ScopeSteps Bot')).toBeVisible();
    expect(section.queryByRole('alert')).not.toBeInTheDocument();
    expect(section.queryByRole('status')).not.toBeInTheDocument();
  });
});
