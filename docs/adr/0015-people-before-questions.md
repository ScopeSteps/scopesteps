# 0015. Say who the speakers are before the agent asks its questions

- Status: Accepted
- Date: 2026-10-19

## Context

[ADR 0012](0012-speaker-identity-confirmed-by-people.md) let an editor confirm who each transcript
speaker is, but decided that "confirming never blocks a run": an unconfirmed speaker reached the
agent as "role unknown". In practice, a new project went straight from adding sources to the
agent's clarifying questions and draft. Who's who was a side task on the People page, so most
runs started with every speaker unconfirmed.

Real transcripts hold names, not roles. A run that starts before anyone has said who the
speakers are asks its questions and reads decision rights from statements whose authors it does
not know. The questions get worse, and a wrong reading of who decides is easy to repeat in every
later run.

## Decision

- **A session goes in this order: sources, then people, then questions.** A draft run (`initial`
  mode) starts only once every speaker in the transcripts it pins has an answer: linked to a
  participant (by an editor or automatically, as in ADR 0012) or marked not a person. Otherwise
  `POST /projects/{id}/runs` is refused with 409 `SPEAKERS_UNCONFIRMED`, with the number of
  unconfirmed speakers and the transcript versions they are in. Nothing is stored or logged.
- **The check is made once, when the run is created.** It uses the identities the run will read,
  in the same request. A run that has started is never stopped by a later change to who's who: a
  speaker whose answer is withdrawn mid-run reaches the agent as "role unknown", as before.
- **A meeting role stays optional.** Saying who someone is is required; their meeting role is
  not, because the editor may not know it, and an honest "role unknown" is better than an
  invented role.
- **Only draft runs are held.** A reply run only reads and cites (ADR 0010). A change run pins the
  baseline's sources, whose speakers were answered before that baseline's draft could start.
- **The app leads with the same order.** After sources, the next step is "Identify the people",
  which opens Who's who for each transcript that still has unconfirmed speakers. The run cannot
  be started from the chat until it is done, and a member without the Editor role is told an
  editor must do it. The server stays the judge; the app only reflects the same rule.

## Consequences

- A run's questions and its people are based on speakers someone has identified. "role unknown"
  now means a participant without a meeting role, not a stranger.
- Starting the first run takes one more step for a project with transcripts. A brief-only project,
  or a transcript without speaker labels, starts as before.
- Tests that start draft runs over a transcript must first answer for its speakers, as a user
  would. The API tests do this with the `confirm_speakers` fixture.
- Evaluation runs build their passages directly and do not go through run creation. Dev packs
  already carry a full speaker mapping (`speakers.yaml`), which `just evals-validate` checks
  against the parser. No prompt changed, so earlier scores stay comparable.
- Revisit if transcripts arrive in volume with many generic labels ("Speaker 1"), where
  answering for each label could become a chore worth a "mark the rest not a person" shortcut.
