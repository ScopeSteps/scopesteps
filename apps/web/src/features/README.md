# Features

One folder per backend module, named in kebab-case: `projects/`, `sources/`, `evidence/`,
`backlog/`, `change-control/`, `agent-runs/`, `activity/` (the audit feed), `discussions/`. Create a folder when its first screen is built.

Today: `agent-runs/` (the chat: the project's stored conversation paged by cursor, with user
messages, cited replies, questions answered or changed from the composer, decisions and run
events; the composer with the API's length limit, the Talk it through and Request a change choice (once a baseline is approved) and Stop; messages
not yet stored kept per tab in session storage to retry with the same `Idempotency-Key`; and the
run details; after a change request, the agent's analysis, the change run's questions, the
candidate's scope-decision cards and, once an approver decides, the `change.approved` or
`change.rejected` event, the one place the thread tells the outcome; a run that stops working
reloads the project's scope state and versions before its new state shows; a question skipped
in the chat and answered on the backlog shows that answer), `backlog/` (a version with
its evidence sheet and the version selector over the project's whole history; on a draft,
editing, suggestion review, decision answers and the approve modal; on an approved version, who
approved it and when, and the export modal; on a change candidate in review, its stable ids,
added, changed and removed tags from the server's change set, the Changes only filter, the
exclusion removed if reversed, the scope-decision card an approver answers, and Reject and
Approve as vN, which reuses the approve modal with a "Scope decision made" check, stays disabled
until the scope decision is made and leaves only Reject after a keep; an approver's answers to the candidate's other open
decisions, while everyone else sees who must answer; a rejected candidate named as one and linked to its change request; and the
comparison
of two approved versions that the Change requests page shows), `change-control/` (the project's
change requests, paged by cursor, each with its status, requester, base version, summary and
outcome (an approved one names its version), the change set and request behind a candidate, and
the impact panel: the server's before-and-after figures as a summary, a chart and text, shown on
each change request, on the Backlog for a candidate in review and, as the summary, in the chat), `sources/` (the sources table, source viewer with
removal, the Add a source modal and its several-file picker, which New project step 2 reuses, and
the cited passages other features show), `identity/` (the user, their role and what it allows, the
names of the project's members, which name every reviewer, the Profile settings form that saves
name, job title and about text to `PATCH /me` and keeps nothing in browser storage, the sign-in
and sign-up forms, confirmation resends, sign-out, the invitation queries and the member and
invitation commands), `projects/` (the project list and detail, the switcher menu, the New
project modal and Project settings with its limits and its Members panel: approvers invite by
email or link with chosen roles, copy, re-send or cancel pending invitations, change roles and
remove members; everyone sees the role tags and may leave; the server judges every action), and the
People page: the people the sources name with their corrections, confirmed rights and evidence
sheet), `discussions/` (threads on an epic or story, opened from the speech bubble with its open
count on each backlog row, and the Discussion page with General discussion and every thread,
filtered Open, Resolved or All: start a thread, reply, edit or delete your own comment after
confirming, resolve and reopen where the role allows; comments are plain text with links, an
unsent comment is kept per tab, and a 409 offers a reload) and `health/`.

Each feature exposes its public components and hooks through `index.ts`. Other features and
`app/` import only from that file; ESLint enforces this.

## What a feature builds on

- **The shell** (`src/app/shell/`) frames every page: sidebar, top bar with the page title, the
  status chip and the "next step" pill. A feature renders the content of a page, never its own
  page chrome, `<main>` or `<h1>`; start at `<h2>`. A page wraps its features in `PageBody`,
  except the chat, which fills the page so its composer stays at the bottom.
- **Shared components** (`src/components/`): `Button`, `ButtonLink`, `IconButton`, `Tag`,
  `DiffTag` (added, changed, removed), `Badge`, `CitationChip`, `Card`, `Banner`, `EmptyState`,
  `SegmentedControl`, `Select`, `Modal`, `SideSheet`, `ToastProvider` with `useToast`, `Avatar`,
  `Icon`. Extend one rather than restyling a copy.
- **Design tokens** (`src/index.css`): colours exist only as token classes such as
  `bg-surface`, `text-muted` and `border-line`. The Tailwind palette is switched off, so
  `text-gray-600` produces nothing.

A new screen joins the sidebar (`src/app/shell/ProjectNav.tsx`) and the routes
(`src/app/routes.ts`) in the pull request that delivers its API, not before.

The project in view is the id in the URL (`/projects/{id}/...`), never browser storage, so a
refresh or a shared link opens the same project. The switcher keeps the page and drops its query
string, which names a run or version of the project being left. Anyone signed in may create a
project and becomes its editor and approver, so New project is offered to viewers too; renaming
needs the editor or approver role, and Project settings is read-only for anyone else.

Controls that change a project (upload, remove a source, start, answer, skip, stop, edit a
draft, correct a person, confirm their rights) appear only for
someone with the editor role there, read with `useCanEdit` from `identity/`; approving a draft
needs the approver role (`useCanApprove`), as does approving or rejecting a change candidate, and answering a draft's decision either role. A
change candidate's scope decision is answered only by an approver
([ADR 0011](../../../../docs/adr/0011-change-requests-and-stable-id-change-sets.md)); everyone
else sees that it waits for a Product owner.
Exporting an approved version, reading the version history and comparing two versions are open
to every member, viewers included. A comparison is always the server's, by stable ids; the page
never compares two versions itself. The API still checks
every request, and a refusal is shown as an error.

Every page except sign-in, sign-up (`/sign-up`), email confirmation (`/verify-email/:token`)
and the invitation page (`/invite/:token`) needs a session (`app/SessionGuard.tsx`). The
invitation page reads the session itself: it offers Join to the invited account, asks another
account to switch, sends a signed-out person with an account to sign in (email prefilled) and
back, and lets someone new create their account and land in the project. A `401` from any request
other than sign-in sends the user to sign-in with the page to come back to, and the sign-in page
drops every cached response; a feature never handles a `401` itself. The session is an HttpOnly
cookie the browser sends by itself: nothing in the app reads, stores or logs a credential.

The People badge counts the people whose decision rights no source states and nobody has
confirmed. Confirming Unknown takes a person off the count: it records that someone looked and
could not say (see `modules/projects/README.md`).

Edits, answers, approvals and changes to a person send the revision on screen. A `409` saying the
draft or person changed is never retried: the page says so and offers a reload, then the
reviewer looks again
([ADR 0008](../../../../docs/adr/0008-atomic-baseline-approval.md)).

How screens look and behave is in the `design-system` skill; code rules are in the
`typescript-react` skill.
