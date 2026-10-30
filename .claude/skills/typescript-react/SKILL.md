---
name: typescript-react
description: Conventions for writing or changing TypeScript and React in ScopeSteps (apps/web, packages/api-client). Use before writing, reviewing or refactoring any .ts or .tsx file, adding a screen, component, hook, API call or Vitest test.
---

# TypeScript and React in ScopeSteps

`apps/web` is a Vite single-page app: React, strict TypeScript, Tailwind, TanStack Query, React
Router, tested with Vitest and Testing Library. pnpm is the package manager.
How screens look and behave, following the v1 prototype, is in the `design-system` skill.

## Where code goes

```text
apps/web/src/
  app/         Routing, providers and pages that compose features
    shell/     The frame around every page: sidebar, top bar, settings, project status
  components/  Shared building blocks with no feature knowledge (Button, Modal, SideSheet)
  features/    One kebab-case folder per backend module (sources/, change-control/, agent-runs/)
  lib/         Cross-feature plumbing, e.g. the typed API client, browser preferences
  test/        Shared test setup (mock server, fixtures, renderApp, accessibility check)
  index.css    Design tokens and their Tailwind mapping
```

- A feature exports its public components and hooks from `index.ts`. `app/` and other features
  import only from that file. ESLint enforces it.
- Create a feature folder when its first screen is built, not before.
- Import across folders with the `@/` alias; use relative paths inside a feature.
- A page is a route in `app/routes.ts` with `handle.title` for the top bar. It wraps its
  features in `PageBody` and renders no `<main>`, `<h1>` or navigation of its own. The chat is
  the exception to `PageBody`: it fills the page so its composer stays at the bottom.
- `components/` and `lib/` import nothing from `app/` or `features/`. A component that needs
  API data belongs in a feature or in the shell.
- The browser stores only what `lib/preferences.ts` holds (theme, accent, sidebar state), the
  last run id and, per tab in session storage, the chat's unsent draft and unconfirmed messages
  and each discussion box's unsent comment.
  Never add project data, profiles or anything the server owns.

## Talking to the API

- Use `api` from `@/lib/api` (openapi-fetch over generated types). Never hand-write a request or
  response type and never call `fetch` directly.
- If the type you need is missing, the backend contract is missing it. Change the API, run
  `just contract`, and use the regenerated types. Do not edit `packages/api-client/src/schema.ts`.
- Wrap each call in a TanStack Query hook inside the feature (`useApiHealth`). Check `error`
  from openapi-fetch and throw, so the query's error state is real.
- Query keys are arrays that start with the feature name: `['sources', projectId, 'list']`.
- Mutations send an `Idempotency-Key`, pass the expected revision for edits and approvals, and
  invalidate the queries they affect. Treat a 409 as "someone changed this": refetch and tell
  the user, do not retry blindly.
- Server state lives in TanStack Query. Do not copy it into `useState` or a store.
- A `401` means the session ended. `lib/api.ts` reports it and `app/SessionGuard.tsx` returns
  to sign-in, which clears the query cache; do not handle a `401` in a feature. The session is
  an HttpOnly cookie: never read, store or log a credential or token in the browser.
- Nothing secret goes in a `VITE_` variable; those are shipped to the browser.

## TypeScript

- Strict mode stays on. No `any`, no non-null `!`, no `as` casts to silence an error. Narrow
  with a type guard or fix the type at its source.
- Use `import type` for type-only imports.
- Prefer a union of string literals to an enum, and a discriminated union to a bag of optional
  fields.
- Let inference work for locals; annotate exported function signatures and component props.

## React

- Function components and hooks only. Named exports, one component per file, file named after
  the component (`HealthStatus.tsx`).
- Derive values during render. Reach for `useEffect` only to sync with something outside React.
- Every screen handles pending, error and empty as well as the happy path.
- Accessibility is part of done: semantic elements, a label for every control, `role="status"`
  for live status text, full keyboard use.
- Style with Tailwind classes in the markup. No inline `style` unless a value is computed.
- Colours come from the design tokens only (`bg-surface`, `text-muted`, `border-accent-line`).
  The Tailwind palette is switched off, so `text-gray-600` silently does nothing. Join
  conditional classes with `cx` from `@/lib/cx`.
- Reuse the shared components before writing markup for a button, tag, card, banner, modal,
  side sheet, toast or empty state. Anything that opens over the page uses `useLayer`, which
  moves focus in, returns it on close and gives Escape to the top layer only.
- Keep components small. Move data fetching into a hook and logic into a plain function that
  can be tested without rendering.

## Tests

- Vitest and Testing Library, next to the code: `HealthStatus.test.tsx`.
- Test what a user sees and does. Query by role and accessible name, not by class or test id.
- Mock the network with the shared server in `src/test/server.ts`; do not mock hooks or the
  `api` client. `projectHandlers()` in `src/test/handlers.ts` serves a project as a page first
  loads it (the user, the project with its limits, the sources); override what a test needs.
- Arrange, act, assert, with names that state the behaviour.
- To test a page inside the shell, render the real routes with `renderApp(path)` from
  `src/test/renderApp.tsx`. Drive keyboard behaviour with `@testing-library/user-event`.
- A new shared component, layer or shell change runs `expectNoAccessibilityViolations()` from
  `src/test/axe.ts` in the states it can be in (closed, open, narrow screen).

## Before you finish

Run `just format`, then `just check`. For a UI change, also run `just api` and `just web` and
look at the screen in a browser; passing type checks do not prove the feature works.
