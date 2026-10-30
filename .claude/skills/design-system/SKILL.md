---
name: design-system
description: How the ScopeSteps web app looks and behaves, following the approved v1 prototype. Use before building or changing any screen, layout, component, colour, theme, copy, modal, sheet or empty state in apps/web, and when porting anything from the prototype.
---

# The ScopeSteps design system

The approved design is the v1 prototype, `docs/design/ScopeSteps-v1.html`. Open it in a browser
to see a screen before building it. Code rules for `apps/web` are in the `typescript-react`
skill; this skill covers what the app looks like and how it behaves.

## The rule everything else follows from

**Copy the prototype's look, never its logic.** The prototype is the reference for layout,
visual design, wording and interaction. Everything it shows is scripted in the browser, so it is
not a reference for data or decisions. The app takes all data and every decision from the API.

## Never port these

- Demo accounts, sample passwords, click-to-fill sign-in, any password check in the browser.
- Hard-coded content: the room-booking brief, transcript, club email, seeded people, questions,
  drafts, the "what I found" list, the scripted change request, and ids like `P3`, `EX-01`,
  `Q1`, `ST-06`.
- Demo controls and copy: "Use example", "Or use the sample", "Reset demo data", the "Demo"
  project tag, and any "scripted", "preview only" or "for demos only" wording.
- The fake agent: timers that pretend to work and scripted replies.
- Limits written into copy (turns, tool calls, words, file size). Show the value the API returns.
- Anything the server owns: ids, content hashes, paragraph splitting, approval checks,
  permission checks, export content.

The browser may store only theme, accent, sidebar state and the last run id, plus, per tab, text
the user typed and has not sent yet (a chat message, a comment). Project data and profiles never
go in browser storage.

## Features without an API

A feature whose endpoint is missing or returns 501 is hidden, or shown as an honest empty or
unavailable state. Never a dead button, placeholder data or a control that ends in a 501. Turn
it on in the pull request that delivers its API.

## Tokens

- The tokens are CSS custom properties in `apps/web/src/index.css`, named by role as in the
  prototype: surfaces (`--bg`, `--surface`,
  `--surface-2`, `--hover`), lines (`--line`, `--line-strong`), text (`--fg`, `--muted`,
  `--subtle`), accent (`--accent` and its `-hover`, `-fg`, `-soft`, `-ink`, `-line`), status
  (`--warn-*`, `--bad-*`, `--ok-*`), plus `--shadow`, `--scrim`, `--font` and `--mono`.
- Use the token classes Tailwind gets from them: `bg-surface`, `text-muted`, `border-line`,
  `bg-accent-soft`, `text-warn-ink`, `shadow-pop`. Never write a hex value or a new shade in a
  component. The Tailwind palette (`slate-500`, `indigo-600`) is switched off and produces
  nothing. If a colour is missing, add a token for its role in both themes; `index.test.ts`
  fails when a token lacks a dark value.
- Themes are light, dark and system (`data-theme` on the root; absent means system), and the
  accent is indigo or teal (`data-accent`). Every token has a value in every combination; check
  new screens in both themes. An element can carry either attribute to preview a choice.
- Figtree and IBM Plex Mono are bundled with the app (`@fontsource`). Never load a font or any
  other asset from a third-party host.
- Status colour has a meaning: warn for something that needs a decision, bad for a failure or
  block, ok for passed or approved. Pair colour with text or an icon, never colour alone.
- Charts use the `--chart-*` tokens (`bg-chart-added`), never status colours. They were checked
  as a set for colour-vision separation on each theme's surface; re-check with the `dataviz`
  skill's validator before changing one. A chart gives its figures as text as well, and has a
  text alternative.
- Type: Figtree for text at a 14px base; IBM Plex Mono with tabular numbers for ids, hashes,
  versions and counts (`font-mono tabular-nums`).

## Layout and components

- Shell: a 248px sidebar (brand, project card, navigation with attention badges, account menu)
  and a top bar (title, version and status chip, "next step" pill). The sidebar collapses on
  desktop and becomes a drawer below 900px.
- The shell is `apps/web/src/app/shell/`. It shows only what the API returns: the project card with
  the project's name and scope status from `GET /projects/{id}` (its menu switches projects and
  opens New project and Project settings), the user from `GET /me`, the role as Product owner
  (approver), Business analyst (editor) or Viewer. The project id stays in the URL; switching
  keeps the page and drops its query string. The status chip, the badges and the pill are
  derived from the run and backlog version in view.
- Build every screen from the shared components in `apps/web/src/components/` (button, tag,
  citation chip, card, banner, side sheet, modal, toast, empty state, segmented control). Extend
  a shared component rather than restyling a copy of it.
- A side sheet holds detail about something on the page (evidence, a source). A modal holds a
  decision or a short form (approve, export, new project). A toast confirms an action that
  already happened; it never carries an error the user must act on.
- Wording follows the prototype: sentence case, plain verbs on buttons ("Approve as v1",
  "Add source"), and the same name for a thing on every screen.

## States

Every screen and component handles loading, empty, error and success:

- Loading keeps the layout still; no spinner covers the page.
- Empty states say what will appear and how to make it appear ("People appear after the first
  run").
- Errors show the server's message and code where they help the user, and what to do next. A
  409 says that someone else changed it and offers to reload.
- Blocked actions stay visible but disabled, with the reason next to them, when the user could
  unblock them; hidden when the user's role can never do it.

## Accessibility

- Focus moves into a sheet or modal and back to its trigger on close. Escape closes the top
  layer only. `Modal`, `SideSheet` and anything else that opens over the page get this from
  `useLayer`; do not handle Escape or focus by hand.
- Set `aria-current` on the active navigation item, `aria-expanded` on toggles, and
  `aria-live` (or `role="status"`) on run progress and toasts.
- Every control has a visible label or an accessible name; the visible focus ring uses the
  accent.
- Honour `prefers-reduced-motion`. Layouts work from 320px wide without horizontal scroll.

## Checklist for any UI change

- Matches the prototype's layout, styling and wording in light and dark, at desktop width and
  below 900px?
- Every value from the API, nothing invented or hard-coded in the browser?
- No demo content, demo copy or dead control? A search of `apps/web/src` for the prototype's
  sample text finds nothing outside tests and fixtures.
- Tokens only, no raw colours?
- Loading, empty, error and blocked states handled?
- Keyboard-only use works and the automated accessibility checks pass?
