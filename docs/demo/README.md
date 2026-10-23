# Capstone demonstration

The POC's demonstration script: what to set up, what to show and say, and what to do when the
live model is unavailable. It runs the agreed flow on the campus room booking pack (POC
Implementation Plan, section 3) in about 12 minutes. The findings to present are in
[POC evaluation](../status/poc-evaluation.md).

## Scope, frozen 2026-10-20

The demonstration shows what P0 delivers and nothing beyond it: text sources, who's who,
clarification, a cited draft, approval of v1, one change request rejected and then approved as
v2, and the Jira CSV export. Not in the demonstration, and not needed for it: hosting, single
sign-on, publishing to Jira (the CSV is imported by hand), streamed replies (SSPOC-58) and the
Groq fallback check (SSPOC-25). None of them blocks the local demonstration.

## Before the demonstration

On the laptop that presents, from a clean clone (see the root [README](../../README.md)):

```sh
just setup                     # dependencies, .env with a sign-in password, migrate, seed
just check                     # everything CI runs
just e2e                       # the whole flow in a browser, on the recorded replay
```

For the live run, set `MODEL_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env` (a Google AI Studio
key on a project with no billing account), then check the model once:

```sh
just probe-model               # spends a little quota
just reset-db                  # an empty project for the demonstration
just api                       # terminal 1
just web                       # terminal 2
```

Open two browser windows side by side: a normal one signed in as `editor@scopesteps.local` (the
Business analyst) and a private one signed in as `approver@scopesteps.local` (the Product
owner). Both use `SEED_ACCOUNT_PASSWORD` from `.env`. Keep these files at hand, from
`evals/datasets/dev/campus-room-booking/`: `brief.md`, `transcript.md` and `change_request.txt`.

## Live, replay or video

Decide before starting, and say which one the audience is seeing.

| Mode           | When                                    | How                                                                                                                        | What to say                                                    |
| -------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Live           | The probe passes                        | `MODEL_PROVIDER=gemini`                                                                                                    | "This is the live agent."                                      |
| Replay         | No network, no quota or the probe fails | `MODEL_PROVIDER=replay` and `MODEL_REPLAY_FILE=e2e/recordings/campus-room-booking.json` in `.env`, then restart `just api` | "This replays a recorded live run; the banner says so."        |
| Recorded video | The laptop itself fails                 | The two videos attached to SSPOC-24 (editor and approver), made with `E2E_VIDEO=on E2E_SLOWMO=600 just e2e`                | "This is a recorded replay of a live run; the banner says so." |

A replay shows "Replay, not a live agent" on every page ([ADR 0018](../adr/0018-labelled-replay-of-a-recorded-run.md)).
It follows the recording only: give the answers below word for word, in the same order, or the
step that differs is refused. Never present a replay or the video as a live run.

## The script

**1. Sources (editor, 1 min).** On Chat, choose Add sources and add `brief.md` and
`transcript.md`. Say: every source gets an id (SRC-1, SRC-2) and numbered paragraphs, which is
what every citation points to.

**2. Who's who (editor, 1 min).** Name the four speakers: Alex Kim (Product owner), Dana Ruiz
(Sponsor), Priya Nair (Developer) and Sam Okafor (End-user representative). Say: the transcript
only has first names; people say who is who, the model never guesses it (ADR 0015).

**3. The agent asks (editor, 2 min).** Start run. The agent reads the sources and asks before it
drafts. Answer the booking-length conflict with "Three hours is the maximum. The brief is out of
date on this point." Answer the cancellation question with "Users can cancel up to one hour
before the start. Cancelling later counts as a no-show. What happens after a no-show is not
decided yet." If it also asks about Outlook calendar sync, choose Skip. Say: an answer becomes
evidence; a skipped question stays open and blocks the stories it affects, never invented.

**4. The cited draft (editor, 2 min).** In the chat, point at "Excluded: Recurring bookings…".
Open the backlog, click a citation chip in Out of scope and show the exact transcript passage in
the evidence sheet. Point at an "Agent suggestion · no source" criterion. Say: every detail links
to a passage or an answer, and what the agent added on its own is labelled and needs a person.
Show "Approval needs a Product owner": the editor cannot approve. Accept the suggestions and
answer the open decisions (no-shows: "No penalty in release one. A no-show is only recorded.").

**5. Approve v1 (approver, 1 min).** Approve as v1… shows the server's checks: structure,
citations, suggestions reviewed, no open decision. Approve. Say: the application approves, not
the model; v1 is read-only and identified by its content hash.

**6. A change, rejected (editor then approver, 2 min).** As the editor, switch the composer to
Change request and paste `change_request.txt`. The analysis finds the earlier exclusion and
proposes one added story, changing nothing else. As the approver, choose Yes, reverse it (only a
Product owner can), open the candidate (stable story ids, the Added tag), then Reject with a
reason. Say: v1 is still the baseline, with the same hash.

**7. The same change, approved as v2 (both, 2 min).** Send the request again. Reverse it,
review the candidate (accept its suggestion, answer the clash question with "A series cannot be
created if any occurrence clashes with an existing booking. Show the user the clashing dates."),
and Approve as v2. Switch the version selector to v1: unchanged.

**8. Export and the record (1 min).** Export, pick v2 and download the CSV for Jira's importer.
Open Activity: who did what, newest first. Say: only approved versions export, and every
decision is attributed to a person.

The two windows do not update each other live: after the approver decides something, reload
the editor's page to show it there, and the other way round.

## When the live model misbehaves

Known and logged; none of them changes approved scope.

- The change request is refused ("did not pass validation"): send it again. It adds a third epic
  in about two runs out of three (SSPOC-83).
- An answered question shows again as an open decision on the backlog: answer it again with the
  same text (SSPOC-84).
- An Answer form on the backlog closes by itself while the page refreshes: open it again
  (SSPOC-90).
- The change analysis asks no follow-up questions (SSPOC-85): say so; the clash rule is then
  settled on the candidate.
- The model is slow or rate-limited: a step can take 30 s, and the work resumes if the page is
  reloaded. If it keeps failing, switch to the replay and say so.

## After the demonstration

`just reset-db` empties the project. Put `.env` back to the provider you use day to day.
