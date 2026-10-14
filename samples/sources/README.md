# Sample source documents

Synthetic files for trying the Sources view by hand (`just api`, `just web`, then open
**Sources** from the home page). All names and organisations are fictional.
`apps/api/tests/test_sources.py` uploads every file here, so the expected results below stay
true.

## Accepted

| Brief            | Transcript             | What to expect                                                                                                |
| ---------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------- |
| `valid/brief.md` | `valid/transcript.txt` | Stored as version 1 of each source. The transcript holds markup and an instruction, both shown as plain text. |

`valid/brief-revised.md` is a revision: send it as the `file` part of
`POST /projects/{id}/sources/{source_id}/versions` for the brief stored above, and the brief
becomes version 2 while the transcript stays at version 1. Uploaded to `POST .../sources` instead,
it would become a second brief.

## Rejected

Upload each file on its own, or with valid files: nothing is stored when any file of an upload
is rejected.

| File                            | Use as     | Response                         |
| ------------------------------- | ---------- | -------------------------------- |
| `rejected/unsupported-type.pdf` | any kind   | 415 `UNSUPPORTED_SOURCE_TYPE`    |
| `rejected/not-utf8.txt`         | any kind   | 422 `SOURCE_UNREADABLE`          |
| `rejected/empty.txt`            | any kind   | 422 `SOURCE_EMPTY`               |
| `rejected/too-many-words.txt`   | transcript | 413 `SOURCE_WORD_LIMIT_EXCEEDED` |

A file over the 512 KiB size limit (413 `SOURCE_TOO_LARGE`) is too big to keep in the
repository. Create one in the git-ignored `var/` folder:

```sh
mkdir -p var && head -c 600000 /dev/zero | tr '\0' 'a' > var/oversized.txt
```

## Adding a sample

Keep files synthetic and small, add a row above, and add the file to `SAMPLE_UPLOADS` in
`apps/api/tests/test_sources.py`.
