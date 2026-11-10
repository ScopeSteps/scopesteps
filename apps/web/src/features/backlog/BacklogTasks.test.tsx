import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  errorBody,
  makeRun,
  PERMISSIONS,
  PROJECT,
  PROJECT_ID,
  REVIEWER_ID,
  STORY_ID,
  VERSION_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, MESSAGES_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Version = components['schemas']['BacklogVersionResponse'];
type ItemPatch = components['schemas']['ItemPatchRequest'];
type StoryTask = components['schemas']['StoryTask'];
type SuggestTasks = components['schemas']['SuggestTasksRequest'];

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const ITEM_URL = `${API}/backlogs/${VERSION_ID}/items/${STORY_ID}`;
const SUGGEST_URL = `${BACKLOG_URL}/task-suggestions`;
const TASK_RUN_ID = '019a3a5e-0000-7000-8000-0000000000f7';
const RUN_URL = `${API}/runs/${TASK_RUN_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const STORY = 'Search for and book a one-off slot';

const SUGGESTED_ID = '019a3a5e-0000-7000-8000-000000000401';
const FLAGGED_ID = '019a3a5e-0000-7000-8000-000000000402';
const WRITTEN_ID = '019a3a5e-0000-7000-8000-000000000403';
const NEW_ID = '019a3a5e-0000-7000-8000-000000000499';

const SUGGESTED: StoryTask = {
  id: SUGGESTED_ID,
  title: 'Build the room search screen',
  origin: 'suggested',
  suggestion: 'pending',
  flag: null,
};
const FLAGGED: StoryTask = {
  id: FLAGGED_ID,
  title: 'Send a text message reminder',
  origin: 'suggested',
  suggestion: 'pending',
  flag: {
    code: 'out_of_scope_work',
    message: 'It names text messages, which this version leaves out of scope.',
  },
};
const WRITTEN: StoryTask = {
  id: WRITTEN_ID,
  title: 'Check overlapping bookings',
  origin: 'person',
  suggestion: null,
  edited_by: REVIEWER_ID,
  flag: null,
};

function taskBlocker(task: StoryTask): components['schemas']['Blocker'] {
  return {
    code: 'suggested_task',
    message: 'A task the agent suggested has not been accepted, edited or deleted',
    item_id: STORY_ID,
    decision_id: null,
    criterion_id: null,
    task_id: task.id,
  };
}

/** The draft with the story's tasks set, and the blockers its pending suggestions raise. */
function withTasks(version: Version, tasks: StoryTask[]): Version {
  const pending = tasks.filter((task) => task.suggestion === 'pending').map(taskBlocker);
  const others = (blockers: Version['blockers']) =>
    blockers.filter((blocker) => blocker.code !== 'suggested_task');
  return {
    ...version,
    blockers: [...others(version.blockers), ...pending],
    items: version.items.map((item) =>
      item.id === STORY_ID
        ? { ...item, tasks, blockers: [...others(item.blockers), ...pending] }
        : item,
    ),
  };
}

/** A draft held the way the server holds it: task edits apply to it and move its revision. */
function serveDraft(tasks: StoryTask[] = [SUGGESTED, FLAGGED, WRITTEN]) {
  let draft = withTasks(structuredClone(BACKLOG), tasks);
  const edits: ItemPatch[] = [];
  server.use(
    http.get(BACKLOG_URL, () => HttpResponse.json(draft)),
    http.patch(ITEM_URL, async ({ request }) => {
      const body = (await request.json()) as ItemPatch;
      edits.push(body);
      if (body.expected_revision !== draft.revision) {
        return HttpResponse.json(errorBody('VERSION_CHANGED', 'The draft changed.'), {
          status: 409,
        });
      }
      const old = draft.items.find((item) => item.id === STORY_ID)?.tasks ?? [];
      const next = (body.tasks ?? []).map((patch): StoryTask => {
        const before = old.find((task) => task.id === patch.id);
        if (!before) {
          return { id: NEW_ID, title: patch.title, origin: 'person', suggestion: null, flag: null };
        }
        const accepted = patch.accept || patch.title !== before.title;
        return {
          ...before,
          title: patch.title,
          suggestion:
            before.suggestion === 'pending' && accepted ? 'accepted' : (before.suggestion ?? null),
        };
      });
      draft = { ...withTasks(draft, next), revision: draft.revision + 1 };
      return HttpResponse.json(draft);
    }),
  );
  return {
    edits,
    current: () => draft,
    /** Suggestions a run saved: the draft gains them and moves on. */
    save: (saved: StoryTask[]) => {
      draft = { ...withTasks(draft, saved), revision: draft.revision + 1 };
    },
    changeElsewhere: () => {
      draft = { ...draft, revision: draft.revision + 1 };
    },
  };
}

function main() {
  return within(screen.getByRole('main'));
}

async function tasksOfStory() {
  return within(await main().findByRole('list', { name: `Tasks for ${STORY}` }));
}

function taskTitles(list: HTMLElement): string[] {
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.textContent);
}

function nth(rows: HTMLElement[], index: number): HTMLElement {
  const row = rows[index];
  if (!row) {
    throw new Error(`No row ${String(index + 1)}`);
  }
  return row;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Tasks under a story', () => {
  it('lists the story’s tasks in order, labels AI suggestions and says why one is flagged', async () => {
    serveDraft();
    renderApp(PAGE);

    const tasks = await tasksOfStory();
    const rows = tasks.getAllByRole('listitem');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent(/^1\.Build the room search screen/);
    expect(rows[1]).toHaveTextContent(/^2\.Send a text message reminder/);
    expect(rows[2]).toHaveTextContent(/^3\.Check overlapping bookings/);
    expect(within(nth(rows, 0)).getByText('Suggested by AI')).toBeInTheDocument();
    expect(within(nth(rows, 2)).queryByText(/Suggested by AI/)).not.toBeInTheDocument();
    expect(rows[1]).toHaveTextContent(
      'Check this task: It names text messages, which this version leaves out of scope.',
    );
    await expectNoAccessibilityViolations();
  });

  it('counts unreviewed tasks as suggestions to review, not as blocked work', async () => {
    serveDraft([SUGGESTED, WRITTEN]);
    renderApp(PAGE);

    await tasksOfStory();
    const story = main().getByRole('button', { name: new RegExp(`^Story ${STORY}`) });
    // The fixture's story has one criterion suggestion and one conflict of its own.
    expect(within(story).getByText('2 suggestions')).toBeInTheDocument();
    expect(within(story).getByText('1 blocked')).toBeInTheDocument();
    expect(main().getAllByText('Waiting on a decision')).toHaveLength(1);
  });

  it('accepts one suggested task and deletes another, keeping the rest as they are', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    const tasks = await tasksOfStory();
    await userEvent.click(
      tasks.getByRole('button', { name: 'Accept task: Build the room search screen' }),
    );
    await waitFor(() => {
      expect(draft.edits).toHaveLength(1);
    });
    expect(draft.edits[0]?.tasks).toEqual([
      { id: SUGGESTED_ID, title: SUGGESTED.title, accept: true },
      { id: FLAGGED_ID, title: FLAGGED.title, accept: false },
      { id: WRITTEN_ID, title: WRITTEN.title, accept: false },
    ]);
    expect(await tasks.findByText('Suggested by AI · accepted')).toBeInTheDocument();

    await userEvent.click(
      tasks.getByRole('button', { name: 'Delete task: Send a text message reminder' }),
    );
    await waitFor(() => {
      expect(draft.edits).toHaveLength(2);
    });
    expect(draft.edits[1]?.tasks?.map((task) => task.id)).toEqual([SUGGESTED_ID, WRITTEN_ID]);
    await waitFor(() => {
      expect(tasks.queryByText('Send a text message reminder')).not.toBeInTheDocument();
    });
  });

  it('adds, rewords, reorders and deletes tasks, saved as one edit', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: `Edit tasks: ${STORY}` }));
    const form = within(main().getByRole('form', { name: `Edit tasks: ${STORY}` }));
    await userEvent.click(form.getByRole('button', { name: 'Delete task 2' }));
    await userEvent.click(form.getByRole('button', { name: 'Move task 2 up' }));
    const first = form.getByRole('textbox', { name: 'Task 2' });
    await userEvent.clear(first);
    await userEvent.type(first, 'Build the search screen with filters');
    await userEvent.click(form.getByRole('button', { name: '+ Add task' }));
    await userEvent.type(form.getByRole('textbox', { name: 'Task 3' }), 'Write the booking API');
    await userEvent.click(form.getByRole('button', { name: 'Save tasks' }));

    await waitFor(() => {
      expect(draft.edits).toHaveLength(1);
    });
    expect(draft.edits[0]?.tasks).toEqual([
      { id: WRITTEN_ID, title: WRITTEN.title, accept: false },
      { id: SUGGESTED_ID, title: 'Build the search screen with filters', accept: false },
      { id: null, title: 'Write the booking API', accept: false },
    ]);
    const list = await main().findByRole('list', { name: `Tasks for ${STORY}` });
    await waitFor(() => {
      expect(taskTitles(list)).toEqual([
        expect.stringContaining('Check overlapping bookings'),
        expect.stringContaining('Build the search screen with filters'),
        expect.stringContaining('Write the booking API'),
      ]);
    });
  });

  it('does not save a task left blank', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: `Edit tasks: ${STORY}` }));
    const form = within(main().getByRole('form', { name: `Edit tasks: ${STORY}` }));
    await userEvent.click(form.getByRole('button', { name: '+ Add task' }));
    await userEvent.click(form.getByRole('button', { name: 'Save tasks' }));

    expect(form.getByText('Enter the task.')).toBeInTheDocument();
    expect(draft.edits).toHaveLength(0);
  });

  it('says someone else changed the draft on a 409 and reloads it on request', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    const tasks = await tasksOfStory();
    draft.changeElsewhere();
    await userEvent.click(
      tasks.getByRole('button', { name: 'Accept task: Build the room search screen' }),
    );

    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent('Someone else changed this draft after you opened it.');
    await userEvent.click(within(alert).getByRole('button', { name: 'Reload' }));
    await waitFor(() => {
      expect(main().queryByText(/Someone else changed this draft/)).not.toBeInTheDocument();
    });
  });

  it('shows tasks to a viewer without any way to change them', async () => {
    serveDraft();
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, role: 'viewer', permissions: PERMISSIONS.viewer }),
      ),
    );
    renderApp(PAGE);

    const tasks = await tasksOfStory();
    expect(tasks.getAllByRole('listitem')).toHaveLength(3);
    expect(tasks.queryByRole('button')).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /Edit tasks/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /Suggest tasks/ })).not.toBeInTheDocument();
  });

  it('shows the tasks of an approved version read-only', async () => {
    serveDraft([{ ...SUGGESTED, suggestion: 'accepted' }, WRITTEN]);
    server.use(
      http.get(BACKLOG_URL, () =>
        HttpResponse.json({
          ...withTasks(structuredClone(BACKLOG), [
            { ...SUGGESTED, suggestion: 'accepted' },
            WRITTEN,
          ]),
          state: 'approved',
        }),
      ),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: new RegExp(`^Story ${STORY}`) }),
    );
    const tasks = await tasksOfStory();
    expect(tasks.getByText('Suggested by AI · accepted')).toBeInTheDocument();
    expect(
      main().queryByRole('button', { name: /Edit tasks|Suggest tasks/ }),
    ).not.toBeInTheDocument();
  });
});

describe('Suggesting tasks with the agent', () => {
  function serveTaskRun(draft: ReturnType<typeof serveDraft>) {
    const started: { key: string | null; body: SuggestTasks }[] = [];
    let advances = 0;
    server.use(
      http.post(SUGGEST_URL, async ({ request }) => {
        started.push({
          key: request.headers.get('Idempotency-Key'),
          body: (await request.json()) as SuggestTasks,
        });
        return HttpResponse.json(
          makeRun({ id: TASK_RUN_ID, mode: 'tasks', stage: 'tasks', status: 'created' }),
          { status: 201 },
        );
      }),
      http.post(`${RUN_URL}/advance`, () => {
        advances += 1;
        draft.save([
          {
            ...SUGGESTED,
            id: '019a3a5e-0000-7000-8000-000000000411',
            title: 'Design the slot list',
          },
        ]);
        return HttpResponse.json(
          makeRun({
            id: TASK_RUN_ID,
            mode: 'tasks',
            stage: 'tasks',
            status: 'completed',
            revision: 2,
          }),
        );
      }),
    );
    return { started, advances: () => advances };
  }

  it('suggests tasks for one story, shows them as they are saved and says they need review', async () => {
    const draft = serveDraft([]);
    const run = serveTaskRun(draft);
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: `Suggest tasks: ${STORY}` }));

    await waitFor(() => {
      expect(run.started).toHaveLength(1);
    });
    expect(run.started[0]?.body).toEqual({ story_ids: [STORY_ID] });
    expect(run.started[0]?.key).toBeTruthy();
    const tasks = await tasksOfStory();
    expect(await tasks.findByText('Design the slot list')).toBeInTheDocument();
    expect(tasks.getByText('Suggested by AI')).toBeInTheDocument();
    expect(run.advances()).toBe(1);
    expect(
      await main().findByText(/Suggested tasks are ready. Accept, reword or delete each one/),
    ).toBeInTheDocument();
  });

  it('suggests tasks for every story of the draft from the header', async () => {
    const draft = serveDraft([]);
    const run = serveTaskRun(draft);
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: 'Suggest tasks for all stories' }),
    );

    await waitFor(() => {
      expect(run.started).toHaveLength(1);
    });
    expect(run.started[0]?.body).toEqual({ story_ids: null });
    expect(await main().findByText('Design the slot list')).toBeInTheDocument();
  });

  it('shows progress and keeps tasks unchanged while the agent works on them', async () => {
    serveDraft([SUGGESTED]);
    server.use(
      http.get(MESSAGES_URL, () =>
        HttpResponse.json({
          messages: [],
          next_cursor: null,
          active_run: { id: TASK_RUN_ID, mode: 'tasks', status: 'running' },
        }),
      ),
      http.get(RUN_URL, () =>
        HttpResponse.json(
          makeRun({ id: TASK_RUN_ID, mode: 'tasks', stage: 'tasks', status: 'running' }),
        ),
      ),
      // The step is still being worked on elsewhere.
      http.post(`${RUN_URL}/advance`, () =>
        HttpResponse.json(errorBody('RUN_BUSY', 'The run is busy.', true), { status: 409 }),
      ),
    );
    renderApp(PAGE);

    expect(await main().findByText(/Suggesting tasks for the stories…/)).toBeInTheDocument();
    expect(main().getByRole('button', { name: 'Suggest tasks for all stories' })).toBeDisabled();
    expect(main().getByRole('button', { name: `Edit tasks: ${STORY}` })).toBeDisabled();
    expect(
      main().getByRole('button', { name: 'Accept task: Build the room search screen' }),
    ).toBeDisabled();
  });

  it('shows why the agent could not start, in the server’s words', async () => {
    serveDraft([]);
    server.use(
      http.post(SUGGEST_URL, () =>
        HttpResponse.json(
          errorBody('AGENT_BUSY', 'The agent is working on something else in this project.'),
          { status: 409 },
        ),
      ),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: 'Suggest tasks for all stories' }),
    );

    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent(
      'The agent could not suggest tasks. The agent is working on something else in this project.',
    );
    await userEvent.click(within(alert).getByRole('button', { name: 'Dismiss' }));
    expect(main().queryByRole('alert')).not.toBeInTheDocument();
  });

  it('offers to try a failed step again', async () => {
    serveDraft([]);
    let advances = 0;
    server.use(
      http.post(SUGGEST_URL, () =>
        HttpResponse.json(makeRun({ id: TASK_RUN_ID, mode: 'tasks', status: 'created' }), {
          status: 201,
        }),
      ),
      http.post(`${RUN_URL}/advance`, () => {
        advances += 1;
        return HttpResponse.json(
          makeRun({
            id: TASK_RUN_ID,
            mode: 'tasks',
            status: advances === 1 ? 'running' : 'completed',
            revision: 1 + advances,
            error:
              advances === 1
                ? { code: 'PROVIDER_UNAVAILABLE', message: 'The model is busy.', retryable: true }
                : null,
          }),
        );
      }),
      http.get(RUN_URL, () =>
        HttpResponse.json(makeRun({ id: TASK_RUN_ID, mode: 'tasks', status: 'completed' })),
      ),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: 'Suggest tasks for all stories' }),
    );
    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent('The model is busy.');
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    await waitFor(() => {
      expect(advances).toBe(2);
    });
  });
});
