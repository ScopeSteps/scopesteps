import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';
import type { Browser, BrowserContext, Locator, Page } from '@playwright/test';

/**
 * The POC's critical flow in a real browser against the real API: sources, who's who, an agent
 * run with clarification, the cited draft reviewed by an editor, v1 approved by a Product owner,
 * a change request rejected while v1 stays, the same request approved as v2, and the export.
 *
 * The agent is a replay of a recorded live run unless E2E_MODE=record (playwright.config.ts). The
 * test answers whatever the agent asks the way the evaluation's scripted reviewer does, from the
 * demo pack, so the same steps work on the live model and, from its recording, offline.
 */

const PACK = fileURLToPath(
  new URL('../../evals/datasets/dev/campus-room-booking/', import.meta.url),
);
const CHANGE_REQUEST = readFileSync(`${PACK}change_request.txt`, 'utf8').trim();
const PASSWORD = process.env.E2E_PASSWORD ?? '';
const REPLAY = process.env.E2E_MODE !== 'record';
const PROJECT = 'Campus Room Booking';

const SPEAKERS: Record<string, [name: string, role: string]> = {
  Alex: ['Alex Kim', 'Product owner'],
  Dana: ['Dana Ruiz', 'Sponsor'],
  Priya: ['Priya Nair', 'Developer'],
  Sam: ['Sam Okafor', 'End-user representative'],
};

type Answers = [pattern: RegExp, answer: string][];

/** The pack's clarification_answers.yaml, chosen by what a question is about. */
const RUN_ANSWERS: Answers = [
  [
    /cancel|no-show/i,
    'Users can cancel up to one hour before the start. Cancelling later counts as a no-show. ' +
      'What happens after a no-show is not decided yet.',
  ],
  [
    /\b(long|length|duration|maximum|hours?)\b/i,
    'Three hours is the maximum. The brief is out of date on this point.',
  ],
];

/**
 * What the people reviewing decide on the backlog: the same answers, the change's own answers,
 * and the one decision the sources leave to them (no-shows), which a Product owner settles.
 */
const REVIEW_ANSWERS: Answers = [
  [/no-show penalty|after a no-show/i, 'No penalty in release one. A no-show is only recorded.'],
  [
    /clash|overlap|conflict(?!ing)/i,
    'A series cannot be created if any occurrence clashes with an existing booking. Show the user the clashing dates.',
  ],
  [/series|occurrence/i, 'Users can cancel a single occurrence or the whole series.'],
  ...RUN_ANSWERS,
];
const FALLBACK_DECISION = 'Not in release one.';

const contexts: BrowserContext[] = [];

// A failure attaches what each person saw. Closing writes each person's video, when recorded.
test.afterEach(async ({ browserName: _ }, testInfo) => {
  if (testInfo.status !== testInfo.expectedStatus) {
    for (const [index, context] of contexts.entries()) {
      for (const page of context.pages()) {
        const path = testInfo.outputPath(`person-${String(index + 1)}.png`);
        await page.screenshot({ path, fullPage: true });
        await testInfo.attach(`person-${String(index + 1)}`, { path, contentType: 'image/png' });
      }
    }
  }
  await Promise.all(contexts.splice(0).map((context) => context.close()));
});

async function signIn(browser: Browser, email: string): Promise<Page> {
  // Each person gets their own context, which does not inherit the config's `use` options.
  const viewport = { width: 1440, height: 900 };
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport,
    ...(process.env.E2E_VIDEO === 'on'
      ? {
          recordVideo: {
            dir: test.info().outputPath(email.split('@')[0] ?? 'video'),
            size: viewport,
          },
        }
      : {}),
  });
  contexts.push(context);
  const page = await context.newPage();
  await page.goto('/');
  await page.getByRole('textbox', { name: 'Email' }).fill(email);
  await page.getByRole('textbox', { name: 'Password' }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Chat', level: 1 })).toBeVisible();
  return page;
}

async function goTo(page: Page, link: 'Chat' | 'Backlog' | 'Change requests') {
  await page.getByRole('navigation', { name: 'Project' }).getByRole('link', { name: link }).click();
  await expect(page.getByRole('heading', { name: link, level: 1 })).toBeVisible();
}

function answerFor(answers: Answers, text: string): string | undefined {
  return answers.find(([pattern]) => pattern.test(text))?.[1];
}

/**
 * Answers each question the agent asks in the chat from `answers`, until `done` shows. A question
 * no answer fits gets `fallback`, or is skipped without one.
 */
async function answerQuestions(
  page: Page,
  done: Locator,
  answers: Answers = RUN_ANSWERS,
  fallback?: string,
) {
  const open = page.getByRole('main').getByRole('article').filter({ hasText: 'Needs an answer' });
  for (;;) {
    await expect(open.first().or(done)).toBeVisible();
    if (await done.isVisible()) {
      return;
    }
    const question = (await open.first().getByRole('heading').textContent()) ?? '';
    // Pinned by position among the cards with this question: `open.first()` moves on once this
    // one is done, and the agent may ask a skipped question again, in a later card.
    const same = page.getByRole('main').getByRole('article', { name: question, exact: true });
    let position = 0;
    while (!(await same.nth(position).getByText('Needs an answer').isVisible())) {
      position += 1;
    }
    const card = same.nth(position);
    const answer = answerFor(answers, question) ?? fallback;
    if (answer) {
      await card.getByRole('button', { name: 'Answer' }).click();
      await page.getByRole('textbox', { name: 'Message ScopeSteps' }).fill(answer);
      await page.getByRole('button', { name: 'Send' }).click();
    } else {
      await card.getByRole('button', { name: 'Skip' }).click();
    }
    await expect(card.getByText('Needs an answer')).toBeHidden();
  }
}

/**
 * What a person does before approval: accept each agent suggestion and answer each open
 * decision on the backlog. Both are recorded as human decisions.
 */
async function reviewOnBacklog(page: Page) {
  const main = page.getByRole('main');
  for (;;) {
    const accept = main.getByRole('button', { name: /^Accept suggestion/ }).first();
    if (!(await accept.isVisible())) {
      break;
    }
    const name = (await accept.getAttribute('aria-label')) ?? '';
    await accept.click();
    await expect(main.getByRole('button', { name, exact: true })).toBeHidden();
  }
  for (;;) {
    const open = main.getByRole('button', { name: /^Answer: / }).first();
    if (!(await open.isVisible())) {
      break;
    }
    const name = (await open.getAttribute('aria-label')) ?? '';
    const form = main.getByRole('form', { name });
    const buttons = main.getByRole('button', { name, exact: true });
    const offered = await buttons.count();
    await open.click();
    await form
      .getByRole('textbox', { name: 'Your answer' })
      .fill(answerFor(REVIEW_ANSWERS, name) ?? FALLBACK_DECISION);
    await form.getByRole('button', { name: 'Save answer' }).click();
    await expect(form).toBeHidden();
    // The form closes before the saved version renders. Once it has, the answered decision offers
    // no Answer anywhere and the stories it no longer blocks have closed, so the next button
    // clicked is one the page keeps. Another open decision may share the subject.
    await expect.poll(() => buttons.count()).toBeLessThan(offered);
  }
  await expect(main.getByText(/items? needs? attention/)).toBeHidden();
}

/**
 * Sends the change request, answers what the change analysis asks, and waits for its analysis. A
 * change set the server refuses (a known model failure, see e2e/README.md) is sent again, at most
 * three times in all.
 */
async function requestChange(page: Page) {
  const main = page.getByRole('main');
  const ready = main.getByText('The proposed change is ready for review.');
  const failed = main.getByRole('note').filter({ hasText: 'Run failed' });
  const before = { ready: await ready.count(), failed: await failed.count() };
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const asChange = page.getByRole('button', { name: 'Change request' });
    if ((await asChange.getAttribute('aria-pressed')) !== 'true') {
      await asChange.click();
    }
    await page.getByRole('textbox', { name: 'Message ScopeSteps' }).fill(CHANGE_REQUEST);
    await page.getByRole('button', { name: 'Send' }).click();
    const settled = ready.nth(before.ready).or(failed.nth(before.failed + attempt - 1));
    await answerQuestions(page, settled, REVIEW_ANSWERS, FALLBACK_DECISION);
    await expect(page.getByRole('button', { name: 'Stop the agent' })).toBeHidden();
    await expect
      .poll(
        async () => (await ready.count()) - before.ready + (await failed.count()) - before.failed,
      )
      .toBe(attempt);
    if ((await ready.count()) > before.ready) {
      return;
    }
    await expect(main.getByText('Nothing was approved or changed.').last()).toBeVisible();
  }
  throw new Error('The change request was refused three times');
}

/** The approver reverses the earlier exclusion, as only a Product owner may. */
async function reverseExclusion(page: Page) {
  await goTo(page, 'Chat');
  await page.reload();
  const decision = page.getByRole('article', { name: 'Decision needed: reverse the exclusion?' });
  await expect(
    decision
      .getByRole('paragraph')
      .filter({ hasText: /recurring/i })
      .first(),
  ).toBeVisible();
  await decision.getByRole('button', { name: 'Yes, reverse it' }).click();
  await expect(decision).toHaveCount(0);
  await page
    .getByRole('main')
    .getByRole('link', { name: /^View in Backlog/ })
    .last()
    .click();
  await expect(page.getByRole('heading', { name: 'Candidate v2 (in review)' })).toBeVisible();
}

/** Shows a version on the backlog by the start of its name in the version selector. */
async function showVersion(page: Page, prefix: string) {
  const select = page.getByRole('combobox', { name: 'Version' });
  // By value, the version's id: labels change as the history reloads ("v1 · current baseline"
  // becomes "v1" once v2 is approved).
  const option = select.getByRole('option').filter({ hasText: new RegExp(`^${prefix}\\b`) });
  await expect(option).toHaveCount(1);
  await select.selectOption((await option.getAttribute('value')) ?? '');
}

/** The approved version's short content hash, as the backlog shows it. */
async function contentHash(page: Page): Promise<string> {
  const note = page.getByRole('main').getByText(/^Approved by/);
  const hash = /([0-9a-f]{4}…[0-9a-f]{4})/.exec((await note.textContent()) ?? '')?.[1];
  expect(hash).toBeDefined();
  return hash ?? '';
}

test(`${PROJECT}: sources to an approved, changed and exported backlog`, async ({ browser }) => {
  const editor = await signIn(browser, 'editor@scopesteps.local');
  const approver = await signIn(browser, 'approver@scopesteps.local');
  if (REPLAY) {
    for (const page of [editor, approver]) {
      await expect(page.getByText('Replay, not a live agent.')).toBeVisible();
    }
  }

  await test.step('the editor adds the brief and the transcript', async () => {
    await editor.getByRole('main').getByRole('button', { name: 'Add sources' }).click();
    const dialog = editor.getByRole('dialog', { name: 'Add a source' });
    await dialog
      .locator('input[type=file]')
      .setInputFiles([`${PACK}brief.md`, `${PACK}transcript.md`]);
    await dialog.getByRole('button', { name: 'Add 2 sources' }).click();
    await expect(editor.getByText('SRC-1 brief.md and SRC-2 transcript.md added.')).toBeVisible();
  });

  await test.step("the editor says who's who in the transcript", async () => {
    const dialog = editor.getByRole('dialog', { name: /Who's who in SRC-2/ });
    for (const [label, [name, role]] of Object.entries(SPEAKERS)) {
      await dialog
        .getByRole('combobox', { name: `Who is ${label}?` })
        .selectOption({ label: 'New participant…' });
      await dialog
        .getByRole('textbox', { name: `Name of the new participant for ${label}` })
        .fill(name);
      await dialog.getByRole('combobox', { name: `Meeting role of ${label}` }).fill(role);
    }
    await dialog.getByRole('button', { name: 'Save' }).click();
    await expect(
      editor.getByText('Everyone who speaks in your transcripts is identified'),
    ).toBeVisible();
  });

  await test.step('the agent asks, the editor answers, and the draft excludes recurring bookings', async () => {
    await editor.getByRole('button', { name: 'Start run' }).click();
    const done = editor.getByRole('main').getByRole('link', { name: 'Open backlog' });
    await answerQuestions(editor, done);
    await expect(editor.getByText('The draft backlog is ready for review.')).toBeVisible();
    const found = editor.getByRole('list', { name: 'What the agent found' });
    await expect(
      found.getByRole('listitem').filter({ hasText: /^Excluded.*[Rr]ecurring/ }),
    ).toHaveCount(1);
    await done.click();
  });

  await test.step('the editor checks a citation and reviews the draft, but cannot approve it', async () => {
    const outOfScope = editor.getByRole('list', { name: 'Out of scope' });
    const recurring = outOfScope.getByRole('listitem').filter({ hasText: /[Rr]ecurring/ });
    await recurring
      .getByRole('button', { name: /^Transcript ¶\d+, evidence for/ })
      .first()
      .click();
    const evidence = editor.getByRole('dialog', { name: 'Evidence' });
    await expect(evidence.getByText(/recurring/i).first()).toBeVisible();
    await evidence.getByRole('button', { name: 'Close' }).click();
    await expect(editor.getByText('Approval needs a Product owner')).toBeVisible();
    await expect(editor.getByRole('button', { name: /^Approve/ })).toHaveCount(0);
    await reviewOnBacklog(editor);
  });

  let v1Hash = '';
  await test.step('the Product owner approves v1 once every server check passes', async () => {
    await goTo(approver, 'Backlog');
    await approver.getByRole('button', { name: 'Approve as v1…' }).click();
    const dialog = approver.getByRole('dialog', { name: 'Approve baseline v1' });
    await expect(
      dialog.getByRole('list', { name: 'Approval checks' }).getByText('Passed', { exact: true }),
    ).toHaveCount(4);
    await dialog.getByRole('button', { name: 'Approve as v1' }).click();
    await expect(approver.getByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    v1Hash = await contentHash(approver);
  });

  await test.step('a change request is rejected and v1 stays as it was', async () => {
    await goTo(editor, 'Chat');
    await requestChange(editor);
    await expect(
      editor.getByText('Waiting for a Product owner.', { exact: false }).last(),
    ).toBeVisible();
    await reverseExclusion(approver);
    await approver.getByRole('button', { name: 'Reject…' }).click();
    const dialog = approver.getByRole('dialog', { name: 'Reject Candidate v2' });
    await dialog
      .getByRole('textbox', { name: 'Reason' })
      .fill('Not this term: the clash rules for a series need agreeing first.');
    await dialog.getByRole('button', { name: 'Reject', exact: true }).click();
    // The chat has no push: another person's decision shows once the page loads again.
    await editor.reload();
    await expect(editor.getByText(/CR-1 was rejected; the baseline stays v1\./)).toBeVisible();
    await expect(approver.getByRole('heading', { name: 'Candidate v2 · rejected' })).toBeVisible();
    await showVersion(approver, 'v1');
    await expect(approver.getByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(await contentHash(approver)).toBe(v1Hash);
  });

  await test.step('the same request is approved as v2, and v1 still does not change', async () => {
    await requestChange(editor);
    await reverseExclusion(approver);
    await expect(
      approver.getByText('v1 stays unchanged unless this is approved', { exact: false }),
    ).toBeVisible();
    await reviewOnBacklog(approver);
    await approver.getByRole('button', { name: 'Approve as v2…' }).click();
    const dialog = approver.getByRole('dialog', { name: 'Approve baseline v2' });
    await expect(
      dialog.getByRole('list', { name: 'Approval checks' }).getByText('Passed', { exact: true }),
    ).toHaveCount(5);
    await dialog.getByRole('button', { name: 'Approve as v2' }).click();
    await expect(approver.getByRole('heading', { name: 'Baseline v2' })).toBeVisible();
    await showVersion(approver, 'v1');
    await expect(approver.getByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(await contentHash(approver)).toBe(v1Hash);
  });

  await test.step('any member exports v2 as a Jira CSV, with the added story in it', async () => {
    await goTo(editor, 'Backlog');
    await editor.reload();
    await editor.getByRole('button', { name: 'Export' }).click();
    const dialog = editor.getByRole('dialog', { name: /^Export v\d/ });
    const version = dialog.getByRole('combobox', { name: 'Version' });
    const rows = dialog.getByRole('table', { name: 'Rows of the CSV file' }).getByRole('rowheader');
    await version.selectOption('v1');
    await expect(rows.first()).toBeVisible();
    const v1Rows = await rows.count();
    await version.selectOption('v2');
    await expect.poll(() => rows.count()).toBeGreaterThan(v1Rows);
    const [download] = await Promise.all([
      editor.waitForEvent('download'),
      dialog.getByRole('button', { name: 'Download CSV for Jira' }).click(),
    ]);
    expect(download.suggestedFilename()).toBe('campus-room-booking-backlog-v2.csv');
    const csv = readFileSync((await download.path()) ?? '', 'utf8');
    expect(csv.split('\r\n')[0]).toBe('Issue ID,Issue Type,Summary,Description,Parent');
    expect(csv).toMatch(/recurring|weekly|series/i);
    await dialog.getByRole('button', { name: 'Close' }).first().click();
    await expect(dialog).toBeHidden();
  });

  await test.step('the change requests page shows one rejected and one approved request', async () => {
    await goTo(editor, 'Change requests');
    const main = editor.getByRole('main');
    await expect(main.getByText(/rejected/i).first()).toBeVisible();
    await expect(main.getByText(/approved/i).first()).toBeVisible();
  });
});
