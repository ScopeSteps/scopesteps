import type { components } from '@scopesteps/api-client';
import { configure, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  APPROVER,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  VIEWER,
} from '@/test/fixtures';
import { API, PEOPLE_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type Person = components['schemas']['PersonResponse'];

const PEOPLE_PATH = `/projects/${PROJECT_ID}/people`;
const [DANA_BLOCK, ALEX_BLOCK] = TRANSCRIPT_BLOCKS;

function person(id: string, extracted: Partial<Person['extracted']>, revision = 1): Person {
  const name = extracted.name ?? 'Someone';
  const role = extracted.role ?? '';
  return {
    id: `019a3a5e-0000-7000-8000-0000000002${id}`,
    project_id: PROJECT_ID,
    revision,
    name,
    role,
    extracted: {
      name,
      role,
      said: '',
      stated_rights: 'not_stated',
      evidence: [],
      rights_evidence: [],
      run_id: '019a3a5e-0000-7000-8000-0000000000f1',
      extracted_at: '2026-10-13T09:00:00Z',
      ...extracted,
    },
    correction: null,
    confirmed_rights: null,
    created_at: '2026-10-13T09:00:00Z',
  };
}

const DANA = person('01', {
  name: 'Dana',
  role: 'Facilities',
  said: 'Wants a single booking capped at three hours.',
  evidence: [
    {
      source_version_id: TRANSCRIPT.id,
      block_id: DANA_BLOCK?.id ?? '',
      quote: 'Three hours is the most I want for a single booking.',
      relationship: 'supporting',
    },
  ],
});
const ALEX = person('02', {
  name: 'Alex',
  role: 'Product owner',
  stated_rights: 'decides',
  evidence: [
    {
      source_version_id: TRANSCRIPT.id,
      block_id: ALEX_BLOCK?.id ?? '',
      quote: null,
      relationship: 'supporting',
    },
  ],
  rights_evidence: [
    {
      source_version_id: TRANSCRIPT.id,
      block_id: ALEX_BLOCK?.id ?? '',
      quote: 'Recurring reservations are out of scope for release one.',
      relationship: 'supporting',
    },
  ],
});

function personUrl(target: Person, command: 'correction' | 'rights') {
  return `${PEOPLE_URL}/${target.id}/${command}`;
}

interface Sent {
  key: string | null;
  body: unknown;
}

function serve(people: Person[], user = REVIEWER) {
  // A later `server.use` wins, so the overrides go in after the project's defaults.
  server.use(...projectHandlers());
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(user)),
    http.get(PEOPLE_URL, () => HttpResponse.json({ people })),
  );
}

function card(name: string) {
  return screen.getByRole('article', { name });
}

describe('People page', () => {
  beforeEach(() => {
    // Effects run twice, as in development, so layers and focus survive it.
    configure({ reactStrictMode: true });
  });
  afterEach(() => {
    configure({ reactStrictMode: false });
    resetViewport();
  });

  it('shows each person with their role, rights, status and citations', async () => {
    serve([DANA, ALEX]);

    renderApp(PEOPLE_PATH);

    const dana = await screen.findByRole('article', { name: 'Dana' });
    expect(dana).toHaveTextContent('Facilities');
    expect(dana).toHaveTextContent('Wants a single booking capped at three hours.');
    expect(dana).toHaveTextContent('Not stated');
    expect(dana).toHaveTextContent('No source states their decision rights.');
    expect(
      await within(dana).findByRole('button', { name: 'Transcript ¶1, evidence for: Dana' }),
    ).toBeInTheDocument();

    const alex = card('Alex');
    expect(alex).toHaveTextContent('Stated in source');
    expect(alex).toHaveTextContent('Decides what’s in scope.');
    expect(
      within(alex).getByRole('button', {
        name: 'Transcript ¶2, evidence for: Alex’s decision right',
      }),
    ).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('opens the cited passages in the evidence sheet and returns focus when it closes', async () => {
    serve([DANA, ALEX]);
    renderApp(PEOPLE_PATH);
    const alex = await screen.findByRole('article', { name: 'Alex' });
    const chip = await within(alex).findByRole('button', {
      name: 'Transcript ¶2, evidence for: Alex’s decision right',
    });

    await userEvent.click(chip);

    const sheet = screen.getByRole('dialog', { name: 'Evidence' });
    expect(
      within(sheet).getByRole('heading', { name: 'Where a source states their decision right' }),
    ).toBeInTheDocument();
    expect(within(sheet).getAllByText(/Recurring reservations are out of scope/)).not.toHaveLength(
      0,
    );
    expect(within(sheet).getAllByRole('link', { name: 'Open full source' })[0]).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/sources?version=${TRANSCRIPT.id}&block=${ALEX_BLOCK?.id ?? ''}`,
    );
    await expectNoAccessibilityViolations();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(chip).toHaveFocus();
  });

  it('lets an editor correct a name and role in place, at the revision on screen', async () => {
    const sent: Sent[] = [];
    serve([DANA, ALEX]);
    server.use(
      http.put(personUrl(DANA, 'correction'), async ({ request }) => {
        sent.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
        return HttpResponse.json({
          ...DANA,
          revision: 2,
          name: 'Dana Ruiz',
          role: 'Facilities lead',
          correction: {
            name: 'Dana Ruiz',
            role: 'Facilities lead',
            corrected_by: REVIEWER_ID,
            corrected_at: '2026-10-14T09:00:00Z',
          },
        });
      }),
    );
    renderApp(PEOPLE_PATH);
    await screen.findByRole('article', { name: 'Dana' });

    await userEvent.click(screen.getByRole('button', { name: 'Edit Dana' }));
    const form = screen.getByRole('form', { name: 'Edit Dana' });
    const name = within(form).getByRole('textbox', { name: 'Name' });
    expect(name).toHaveFocus();
    await userEvent.clear(name);
    await userEvent.type(name, '  Dana Ruiz ');
    const role = within(form).getByRole('textbox', { name: 'Role' });
    await userEvent.clear(role);
    await userEvent.type(role, 'Facilities lead');
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }));

    const corrected = await screen.findByRole('article', { name: 'Dana Ruiz' });
    expect(corrected).toHaveTextContent('Facilities lead');
    expect(corrected).toHaveTextContent('Corrected by Local Reviewer');
    expect(within(corrected).getByRole('button', { name: 'Edit Dana Ruiz' })).toHaveFocus();
    expect(sent).toEqual([
      {
        key: expect.stringMatching(/^.{8,}$/) as string,
        body: { name: 'Dana Ruiz', role: 'Facilities lead', expected_revision: 1 },
      },
    ]);
  });

  it('asks for a name before saving a correction', async () => {
    serve([DANA]);
    renderApp(PEOPLE_PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Edit Dana' }));
    const form = screen.getByRole('form', { name: 'Edit Dana' });

    await userEvent.clear(within(form).getByRole('textbox', { name: 'Name' }));
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }));

    expect(within(form).getByRole('textbox', { name: 'Name' })).toHaveAccessibleDescription(
      'Enter a name.',
    );
    await userEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Edit Dana' })).toHaveFocus();
  });

  it('confirms decision rights a source does not state, and the badge counts what is left', async () => {
    const sent: Sent[] = [];
    const sam = person('03', { name: 'Sam', role: 'Student union' });
    serve([DANA, ALEX, sam]);
    server.use(
      http.put(personUrl(DANA, 'rights'), async ({ request }) => {
        sent.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
        return HttpResponse.json({
          ...DANA,
          revision: 2,
          confirmed_rights: {
            rights: 'decides',
            confirmed_by: REVIEWER_ID,
            confirmed_at: '2026-10-14T09:00:00Z',
          },
        });
      }),
    );
    renderApp(PEOPLE_PATH);
    await screen.findByRole('article', { name: 'Dana' });
    expect(await screen.findByRole('link', { name: 'People 2 need attention' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(
      within(card('Alex')).queryByRole('group', { name: /Decision rights/ }),
    ).not.toBeInTheDocument();

    const rights = within(card('Dana')).getByRole('group', { name: 'Decision rights for Dana' });
    for (const option of ['Decides', 'Advises', 'Unknown']) {
      expect(within(rights).getByRole('button', { name: option })).toHaveAttribute(
        'aria-pressed',
        'false',
      );
    }
    await userEvent.click(within(rights).getByRole('button', { name: 'Decides' }));

    await waitFor(() => {
      expect(within(rights).getByRole('button', { name: 'Decides' })).toHaveAttribute(
        'aria-pressed',
        'true',
      );
    });
    expect(card('Dana')).toHaveTextContent('Confirmed');
    expect(card('Dana')).toHaveTextContent('Rights confirmed by Local Reviewer');
    expect(screen.getByRole('link', { name: 'People 1 needs attention' })).toBeInTheDocument();
    expect(sent).toEqual([
      {
        key: expect.stringMatching(/^.{8,}$/) as string,
        body: { rights: 'decides', expected_revision: 1 },
      },
    ]);
  });

  it('says someone else changed the person on a 409 and reloads instead of retrying', async () => {
    let attempts = 0;
    let latest = DANA;
    serve([DANA]);
    server.use(
      http.get(PEOPLE_URL, () => HttpResponse.json({ people: [latest] })),
      http.put(personUrl(DANA, 'rights'), () => {
        attempts += 1;
        latest = { ...DANA, revision: 2, name: 'Dana Ruiz' };
        return HttpResponse.json(
          {
            code: 'PERSON_CHANGED',
            message: 'This person changed since you loaded them.',
            retryable: false,
            details: { current_revision: 2 },
          },
          { status: 409 },
        );
      }),
    );
    renderApp(PEOPLE_PATH);
    await screen.findByRole('article', { name: 'Dana' });

    await userEvent.click(screen.getByRole('button', { name: 'Advises' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Someone else changed this person');
    expect(screen.getByRole('button', { name: 'Advises' })).toBeDisabled();
    await userEvent.click(within(alert).getByRole('button', { name: 'Reload' }));

    expect(await screen.findByRole('article', { name: 'Dana Ruiz' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Advises' })).toBeEnabled();
    expect(attempts).toBe(1);
  });

  it.each([
    ['a viewer', VIEWER],
    ['an approver without the editor role', APPROVER],
  ])('shows %s the people without any control to change them', async (_who, user) => {
    serve([DANA, ALEX], user);

    renderApp(PEOPLE_PATH);

    const dana = await screen.findByRole('article', { name: 'Dana' });
    expect(within(dana).queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument();
    expect(within(dana).queryByRole('group')).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'People named in your sources, with their role and any decision rights the sources state.',
      ),
    ).toBeInTheDocument();
    expect(await within(dana).findByRole('button', { name: /evidence for: Dana/ })).toBeEnabled();
  });

  it('explains that people appear after the first run when nobody is named yet', async () => {
    serve([]);

    renderApp(PEOPLE_PATH);

    expect(await screen.findByRole('heading', { name: 'No people yet' })).toBeInTheDocument();
    expect(screen.getByText(/After the agent’s first run/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^People/ })).toHaveAccessibleName('People');
  });

  it('shows the server’s message when the people cannot be loaded, and tries again', async () => {
    let calls = 0;
    serve([]);
    server.use(
      http.get(PEOPLE_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              {
                code: 'SERVICE_UNAVAILABLE',
                message: 'The database is not reachable.',
                retryable: true,
                details: {},
              },
              { status: 503 },
            )
          : HttpResponse.json({ people: [DANA] });
      }),
    );
    renderApp(PEOPLE_PATH);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The database is not reachable.');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('article', { name: 'Dana' })).toBeInTheDocument();
  });

  it('passes the accessibility checks on a narrow screen with a person being edited', async () => {
    setNarrowViewport(true);
    serve([DANA, ALEX]);
    renderApp(PEOPLE_PATH);

    await userEvent.click(await screen.findByRole('button', { name: 'Edit Dana' }));

    expect(screen.getByRole('form', { name: 'Edit Dana' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });
});
