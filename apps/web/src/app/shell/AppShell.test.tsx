import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  BRIEF,
  CANCEL_QUESTION,
  errorBody,
  LENGTH_QUESTION,
  makeRun,
  PROJECT,
  PROJECT_ID,
  REVIEWER,
  RUN_ID,
  TRANSCRIPT,
  VERSION_ID,
} from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

const SOURCES_URL = `/projects/${PROJECT_ID}/sources`;
const BACKLOG_URL = `/projects/${PROJECT_ID}/backlog`;
const CHAT_URL = `/projects/${PROJECT_ID}/chat`;
const LAST_RUN_KEY = `scopesteps:last-run:${PROJECT_ID}`;
const PREFERENCES_KEY = 'scopesteps:preferences';

function sidebar() {
  return screen.getByRole('complementary', { name: 'Main navigation' });
}

function accountButton() {
  return screen.findByRole('button', { name: /Local Reviewer/ });
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
    http.get(`*/api/v1/projects/${PROJECT_ID}`, () => HttpResponse.json(PROJECT)),
    http.get(`*/api/v1/projects/${PROJECT_ID}/sources`, () =>
      HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] }),
    ),
    http.get('*/api/v1/projects/:projectId/sources/:versionId/blocks', () => HttpResponse.json([])),
    http.get(`*/api/v1/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
      HttpResponse.json(BACKLOG),
    ),
  );
});

afterEach(() => {
  resetViewport();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('data-accent');
});

describe('AppShell', () => {
  it('frames the page with the brand, the project, the navigation and the signed-in user', async () => {
    renderApp(SOURCES_URL);

    expect(await accountButton()).toHaveTextContent('Business analyst');
    expect(screen.getByRole('heading', { level: 1, name: 'Sources' })).toBeInTheDocument();
    expect(within(sidebar()).getByRole('link', { name: 'ScopeSteps' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(
      await within(sidebar()).findByRole('button', {
        name: `Project ${PROJECT.name} No baseline yet`,
      }),
    ).toHaveAttribute('aria-haspopup', 'menu');

    const nav = screen.getByRole('navigation', { name: 'Project' });
    expect(within(nav).getByRole('link', { name: 'Sources' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Backlog' })).not.toHaveAttribute('aria-current');
    expect(within(nav).getByRole('link', { name: 'Backlog' })).toHaveAttribute('href', BACKLOG_URL);
    expect(screen.getByRole('main')).toContainElement(
      await screen.findByRole('heading', { name: 'Stored sources' }),
    );
  });

  it('has no accessibility violations, with the menu and the settings open too', async () => {
    renderApp(SOURCES_URL);
    await screen.findByRole('heading', { name: 'Stored sources' });
    await expectNoAccessibilityViolations();

    await userEvent.click(await accountButton());
    await expectNoAccessibilityViolations();

    await userEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
    expect(screen.getByRole('dialog', { name: 'Your settings' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('offers only what the API can do today', async () => {
    renderApp(SOURCES_URL);
    await userEvent.click(await accountButton());

    const links = within(screen.getByRole('navigation', { name: 'Project' })).getAllByRole('link');
    expect(links.map((link) => link.textContent.trim())).toEqual([
      'Chat',
      'Backlog',
      'Change requests',
      'Sources',
      'People',
      'Activity',
    ]);
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
      'Settings',
      'Sign out',
    ]);
    for (const absent of [/profile/i, /export/i, /approve/i]) {
      expect(within(sidebar()).queryByText(absent)).not.toBeInTheDocument();
    }
  });

  describe('project status', () => {
    it('points at adding sources while the project has none', async () => {
      server.use(
        http.get(`*/api/v1/projects/${PROJECT_ID}/sources`, () =>
          HttpResponse.json({ source_versions: [] }),
        ),
      );

      renderApp(BACKLOG_URL);

      expect(await screen.findByRole('link', { name: 'Add sources' })).toHaveAttribute(
        'href',
        SOURCES_URL,
      );
      expect(within(screen.getByRole('banner')).getByText('Setting up')).toBeInTheDocument();
    });

    it('points at starting a run once sources are stored', async () => {
      renderApp(SOURCES_URL);

      expect(await screen.findByRole('link', { name: 'Start the agent run' })).toHaveAttribute(
        'href',
        CHAT_URL,
      );
    });

    it('counts the open questions of the last run started in this browser', async () => {
      window.localStorage.setItem(LAST_RUN_KEY, RUN_ID);
      server.use(
        http.get(`*/api/v1/runs/${RUN_ID}`, () =>
          HttpResponse.json(
            makeRun({
              status: 'waiting_for_input',
              questions: [CANCEL_QUESTION, LENGTH_QUESTION],
            }),
          ),
        ),
      );

      renderApp(SOURCES_URL);

      const runUrl = `${CHAT_URL}?run=${RUN_ID}`;
      expect(await screen.findByRole('link', { name: 'Answer 2 questions' })).toHaveAttribute(
        'href',
        runUrl,
      );
      expect(screen.getByRole('link', { name: 'Chat 2 need attention' })).toHaveAttribute(
        'href',
        runUrl,
      );
      expect(screen.getByRole('link', { name: 'Backlog' })).toHaveAttribute(
        'href',
        `${BACKLOG_URL}?run=${RUN_ID}`,
      );
      expect(within(screen.getByRole('banner')).getByText('Waiting for you')).toBeInTheDocument();
    });

    it("shows the draft's state, revision and blockers as the API returns them", async () => {
      const blockers = String(BACKLOG.blockers.length);

      renderApp(`${BACKLOG_URL}?version=${VERSION_ID}`);

      expect(
        await screen.findByRole('link', { name: `Review ${blockers} blockers` }),
      ).toBeVisible();
      expect(
        within(screen.getByRole('banner')).getByText('Draft r1 · not approved'),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('link', { name: `Backlog ${blockers} need attention` }),
      ).toHaveAttribute('aria-current', 'page');
    });

    it('reads the version in a sources link as a source, not as a backlog', async () => {
      let backlogRequests = 0;
      server.use(
        http.get('*/api/v1/projects/:projectId/backlogs/:versionId', () => {
          backlogRequests += 1;
          return HttpResponse.json(errorBody('NOT_FOUND', 'No such backlog version.'), {
            status: 404,
          });
        }),
      );

      renderApp(`${SOURCES_URL}?version=${TRANSCRIPT.id}`);

      expect(await screen.findByRole('link', { name: 'Start the agent run' })).toBeInTheDocument();
      expect(backlogRequests).toBe(0);
    });

    it('offers the run details in the top bar only on the chat with a run', async () => {
      server.use(
        http.get(`*/api/v1/runs/${RUN_ID}`, () =>
          HttpResponse.json(makeRun({ status: 'waiting_for_input', questions: [CANCEL_QUESTION] })),
        ),
      );

      renderApp(`${CHAT_URL}?run=${RUN_ID}`);

      const banner = within(screen.getByRole('banner'));
      expect(await banner.findByRole('button', { name: 'Run details' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Chat 1 needs attention' })).toHaveAttribute(
        'aria-current',
        'page',
      );
      await expectNoAccessibilityViolations();
    });

    it('leaves the run details out of other pages', async () => {
      window.localStorage.setItem(LAST_RUN_KEY, RUN_ID);
      server.use(
        http.get(`*/api/v1/runs/${RUN_ID}`, () =>
          HttpResponse.json(makeRun({ status: 'waiting_for_input', questions: [CANCEL_QUESTION] })),
        ),
      );

      renderApp(SOURCES_URL);

      expect(await screen.findByRole('link', { name: 'Answer 1 question' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Run details' })).not.toBeInTheDocument();
    });

    it('tells a viewer that the project is view only', async () => {
      server.use(
        http.get('*/api/v1/me', () =>
          HttpResponse.json({
            ...REVIEWER,
            memberships: [{ project_id: PROJECT_ID, role: 'viewer' }],
          }),
        ),
      );

      renderApp(SOURCES_URL);

      expect(await screen.findByText('View only')).toBeInTheDocument();
      expect(await accountButton()).toHaveTextContent('Viewer');
    });
  });

  describe('sidebar', () => {
    it('hides and shows on desktop, moves focus with it and remembers the choice', async () => {
      renderApp(SOURCES_URL);
      await accountButton();

      const hide = screen.getByRole('button', { name: 'Hide sidebar' });
      expect(hide).toHaveAttribute('aria-expanded', 'true');
      hide.focus();
      await userEvent.keyboard('{Enter}');

      expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
      const show = screen.getByRole('button', { name: 'Show sidebar' });
      expect(show).toHaveAttribute('aria-expanded', 'false');
      expect(show).toHaveFocus();
      expect(window.localStorage.getItem(PREFERENCES_KEY)).toContain('"sidebarCollapsed":true');

      await userEvent.keyboard('{Enter}');

      expect(sidebar()).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Hide sidebar' })).toHaveFocus();
      expect(screen.queryByRole('button', { name: 'Show sidebar' })).not.toBeInTheDocument();
    });

    it('starts hidden when the user left it hidden', async () => {
      window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ sidebarCollapsed: true }));

      renderApp(SOURCES_URL);

      expect(await screen.findByRole('button', { name: 'Show sidebar' })).toBeInTheDocument();
      expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    });

    it('is a drawer on a narrow screen: closed at first, focus moves in, Escape closes it', async () => {
      setNarrowViewport(true);
      renderApp(SOURCES_URL);
      await screen.findByRole('heading', { name: 'Stored sources' });

      expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
      const open = screen.getByRole('button', { name: 'Open menu' });
      expect(open).toHaveAttribute('aria-expanded', 'false');
      open.focus();
      await userEvent.keyboard('{Enter}');

      expect(sidebar()).toBeInTheDocument();
      expect(open).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('button', { name: 'Close menu' })).toHaveFocus();
      await accountButton();
      await expectNoAccessibilityViolations();

      await userEvent.keyboard('{Escape}');

      expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
      expect(open).toHaveFocus();
      // Opening and closing the drawer is not a preference.
      expect(window.localStorage.getItem(PREFERENCES_KEY)).toContain('"sidebarCollapsed":false');
    });

    it('closes the drawer when the user picks a page', async () => {
      setNarrowViewport(true);
      const router = renderApp(SOURCES_URL);
      await userEvent.click(await screen.findByRole('button', { name: 'Open menu' }));

      await userEvent.click(screen.getByRole('link', { name: 'Backlog' }));

      await waitFor(() => {
        expect(router.state.location.pathname).toBe(BACKLOG_URL);
      });
      expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    });
  });

  describe('account menu', () => {
    it('opens from the keyboard with the user and their email, and Escape returns focus', async () => {
      renderApp(SOURCES_URL);
      const account = await accountButton();
      expect(account).toHaveAttribute('aria-expanded', 'false');

      account.focus();
      await userEvent.keyboard('{Enter}');

      const menu = screen.getByRole('menu', { name: 'Account' });
      expect(account).toHaveAttribute('aria-expanded', 'true');
      expect(menu).toHaveTextContent(REVIEWER.email);
      expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveFocus();

      await userEvent.keyboard('{Escape}');

      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
      expect(account).toHaveFocus();
      expect(sidebar()).toBeInTheDocument();
    });

    it('closes when focus leaves it', async () => {
      renderApp(SOURCES_URL);
      await userEvent.click(await accountButton());
      expect(screen.getByRole('menu')).toBeInTheDocument();

      await userEvent.click(screen.getByRole('heading', { level: 1 }));

      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('offers a retry when the account cannot be loaded', async () => {
      let healthy = false;
      server.use(
        http.get('*/api/v1/me', () =>
          healthy
            ? HttpResponse.json(REVIEWER)
            : HttpResponse.json(errorBody('UNAVAILABLE', 'Try again shortly.', true), {
                status: 503,
              }),
        ),
      );
      renderApp(SOURCES_URL);

      expect(await screen.findByText('Could not load your account.')).toBeInTheDocument();
      healthy = true;
      await userEvent.click(within(sidebar()).getByRole('button', { name: 'Try again' }));

      expect(await accountButton()).toBeInTheDocument();
    });
  });

  describe('appearance settings', () => {
    async function openSettings() {
      const account = await accountButton();
      account.focus();
      await userEvent.keyboard('{Enter}');
      await userEvent.keyboard('{Enter}');
      await userEvent.click(
        within(screen.getByRole('navigation', { name: 'Settings sections' })).getByRole('button', {
          name: 'Appearance',
        }),
      );
      return account;
    }

    it('opens on the profile with focus on its title', async () => {
      renderApp(SOURCES_URL);
      const account = await accountButton();
      account.focus();
      await userEvent.keyboard('{Enter}');
      await userEvent.keyboard('{Enter}');

      expect(screen.getByRole('heading', { name: 'Your settings' })).toHaveFocus();
      expect(
        within(screen.getByRole('navigation', { name: 'Settings sections' })).getByRole('button', {
          name: 'Profile',
        }),
      ).toHaveAttribute('aria-current', 'page');
    });

    it('returns focus to the account button on Escape', async () => {
      renderApp(SOURCES_URL);
      const account = await openSettings();

      expect(
        within(screen.getByRole('navigation', { name: 'Settings sections' })).getByRole('button', {
          name: 'Appearance',
        }),
      ).toHaveAttribute('aria-current', 'page');

      await userEvent.keyboard('{Escape}');

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(account).toHaveFocus();
    });

    it('applies the chosen theme and accent at once and remembers them', async () => {
      renderApp(SOURCES_URL);
      await openSettings();
      const root = document.documentElement;
      expect(screen.getByRole('radio', { name: 'System' })).toBeChecked();
      expect(root).not.toHaveAttribute('data-theme');

      await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));
      await userEvent.click(screen.getByRole('radio', { name: 'Teal' }));

      expect(root).toHaveAttribute('data-theme', 'dark');
      expect(root).toHaveAttribute('data-accent', 'teal');
      expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? '{}')).toEqual({
        theme: 'dark',
        accent: 'teal',
        sidebarCollapsed: false,
      });

      await userEvent.click(screen.getByRole('radio', { name: 'System' }));

      expect(root).not.toHaveAttribute('data-theme');
    });

    it('can be driven with the arrow keys inside a named group', async () => {
      renderApp(SOURCES_URL);
      await openSettings();

      const theme = screen.getByRole('group', { name: 'Theme' });
      within(theme).getByRole('radio', { name: 'System' }).focus();
      await userEvent.keyboard('{ArrowLeft}');

      expect(within(theme).getByRole('radio', { name: 'Dark' })).toBeChecked();
      expect(screen.getByRole('group', { name: 'Accent color' })).toBeInTheDocument();
    });
  });

  it('keeps only the preferences and the last run id in browser storage', async () => {
    window.localStorage.setItem(LAST_RUN_KEY, RUN_ID);
    server.use(
      http.get(`*/api/v1/runs/${RUN_ID}`, () =>
        HttpResponse.json(
          makeRun({ status: 'ready_for_review', candidate_version_id: VERSION_ID }),
        ),
      ),
    );

    renderApp(`${BACKLOG_URL}?run=${RUN_ID}`);
    await screen.findAllByText('Draft r1 · not approved');
    await userEvent.click(screen.getByRole('button', { name: 'Hide sidebar' }));

    expect(Object.keys(window.localStorage).sort()).toEqual([LAST_RUN_KEY, PREFERENCES_KEY].sort());
    expect(window.sessionStorage).toHaveLength(0);
  });
});
