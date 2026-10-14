# Features

One folder per backend module, named in kebab-case: `projects/`, `sources/`, `evidence/`,
`backlog/`, `change-control/`, `agent-runs/`, `activity/` (the audit feed). Create a folder when its first screen is built.

Today: `agent-runs/` (the chat, its composer and the run details), `backlog/` (the draft and its
evidence sheet), `sources/` (the sources table, source viewer, Add sources modal and the cited
passages other features show), `identity/` (the user and their role), `projects/` (the project
detail and its limits) and `health/`.

Each feature exposes its public components and hooks through `index.ts`. Other features and
`app/` import only from that file; ESLint enforces this.

## What a feature builds on

- **The shell** (`src/app/shell/`) frames every page: sidebar, top bar with the page title, the
  status chip and the "next step" pill. A feature renders the content of a page, never its own
  page chrome, `<main>` or `<h1>`; start at `<h2>`. A page wraps its features in `PageBody`,
  except the chat, which fills the page so its composer stays at the bottom.
- **Shared components** (`src/components/`): `Button`, `ButtonLink`, `IconButton`, `Tag`, `Badge`,
  `CitationChip`, `Card`, `Banner`, `EmptyState`, `SegmentedControl`, `Modal`, `SideSheet`,
  `ToastProvider` with `useToast`, `Avatar`, `Icon`. Extend one rather than restyling a copy.
- **Design tokens** (`src/index.css`): colours exist only as token classes such as
  `bg-surface`, `text-muted` and `border-line`. The Tailwind palette is switched off, so
  `text-gray-600` produces nothing.

A new screen joins the sidebar (`src/app/shell/ProjectNav.tsx`) and the routes
(`src/app/routes.ts`) in the pull request that delivers its API, not before.

Controls that change a project (upload, start, answer, skip, stop) appear only for someone with
the editor role there, read with `useCanEdit` from `identity/`. The API still checks every
request, and a refusal is shown as an error.

How screens look and behave is in the `design-system` skill; code rules are in the
`typescript-react` skill.
