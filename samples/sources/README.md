# Sample source documents

Synthetic files for trying the Sources view by hand (`just api`, `just web`, then open
**Sources** from the home page). All names and organisations are fictional.
`apps/api/tests/test_sources.py` uploads every file here, so the expected results below stay
true.

## Accepted

| Brief              | Transcript              | What to expect                                                                                                        |
| ------------------ | ----------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `valid/brief.md`   | `valid/transcript.txt`  | Stored as version 1 of each source. The transcript holds markup and an instruction, both shown as plain text.         |
| `valid/brief.docx` | `valid/transcript.vtt`  | The Word brief keeps its paragraphs and table. The WebVTT captions become one paragraph per turn, each with its time. |
| `valid/brief.pdf`  | `valid/transcript.docx` | Each PDF paragraph shows its page. The Teams Word transcript keeps each header with its turn and time.                |

Like a real meeting export, each transcript names its speakers (`Mira:` in the text file, `Mira
Holt` in the WebVTT and Word ones) but not who they are.
Before the agent run can start, say who each one is in Who's who (ADR 0015). To follow the
sample, use:

| Speaker | Participant | Meeting role        |
| ------- | ----------- | ------------------- |
| Mira    | Mira Holt   | Workshop lead       |
| Tomas   | Tomas Reed  | Front desk          |
| Ana     | Ana Lund    | Volunteer developer |

`valid/brief-revised.md` is a revision: send it as the `file` part of
`POST /projects/{id}/sources/{source_id}/versions` for the brief stored above, and the brief
becomes version 2 while the transcript stays at version 1. Uploaded to `POST .../sources` instead,
it would become a second brief.

## Rejected

Upload each file on its own, or with valid files: nothing is stored when any file of an upload
is rejected.

| File                              | Use as   | Response                        |
| --------------------------------- | -------- | ------------------------------- |
| `rejected/unsupported-type.rtf`   | any kind | 415 `UNSUPPORTED_SOURCE_TYPE`   |
| `rejected/renamed-text.docx`      | any kind | 415 `SOURCE_TYPE_MISMATCH`      |
| `rejected/scanned.pdf`            | any kind | 422 `SOURCE_SCANNED`            |
| `rejected/password-protected.pdf` | any kind | 422 `SOURCE_PASSWORD_PROTECTED` |
| `rejected/not-utf8.txt`           | any kind | 422 `SOURCE_UNREADABLE`         |
| `rejected/empty.txt`              | any kind | 422 `SOURCE_EMPTY`              |

A text file over the 512 KiB size limit (413 `SOURCE_TOO_LARGE`) is too big to keep in the
repository; Word, PDF and WebVTT files may be up to 10 MiB. Create one in the git-ignored `var/` folder:

```sh
mkdir -p var && head -c 600000 /dev/zero | tr '\0' 'a' > var/oversized.txt
```

A project's sources may hold 60,000 words together (413 `SOURCE_WORD_LIMIT_EXCEEDED` beyond
that); a file that large is not kept here either. Create one with 60,001 words:

```sh
mkdir -p var && yes word | head -n 60001 | tr '\n' ' ' > var/too-many-words.txt
```

## Adding a sample

Keep files synthetic and small, add a row above, and add the file to `SAMPLE_UPLOADS` in
`apps/api/tests/test_sources.py`.
