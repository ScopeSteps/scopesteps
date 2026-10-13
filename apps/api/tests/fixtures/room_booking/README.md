# Room-booking run fixture

A scripted agent run over the campus room-booking sources (synthetic; the same brief and
transcript as `evals/datasets/dev/campus-room-booking`). No model wrote these files.

| File                 | Stands for                                                                        |
| -------------------- | --------------------------------------------------------------------------------- |
| `brief.md`           | The uploaded project brief (blocks B1 to B10)                                     |
| `transcript.md`      | The uploaded meeting transcript (blocks B11 to B27)                               |
| `clarification.json` | The arguments of the agent's `request_clarification` call                         |
| `draft.json`         | The draft after the cancellation answer (A1) and the skipped length question (U1) |

`draft.json` deliberately contains one criterion that states a disputed value ("up to 4 hours"),
so tests can show the harness withholding it.
