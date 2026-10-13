# Sample source documents

Synthetic files for trying the Sources view by hand (`just api`, `just web`, then open
**Sources** from the home page). All names and organisations are fictional.
`apps/api/tests/test_sources.py` uploads every file here, so the expected results below stay
true.

## Accepted

| Brief                    | Transcript             | What to expect                                                                                                |
| ------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------- |
| `valid/brief.md`         | `valid/transcript.txt` | Stored as version 1 of each source. The transcript holds markup and an instruction, both shown as plain text. |
| `valid/brief-revised.md` | `valid/transcript.txt` | Upload after the row above: the brief becomes version 2, the unchanged transcript stays at version 1.         |

## Rejected

Pair each file with a valid one for the other input. Nothing is stored when an upload is
rejected.

| File                            | Use as     | Response                         |
| ------------------------------- | ---------- | -------------------------------- |
| `rejected/unsupported-type.pdf` | either     | 415 `UNSUPPORTED_SOURCE_TYPE`    |
| `rejected/not-utf8.txt`         | either     | 422 `SOURCE_UNREADABLE`          |
| `rejected/empty.txt`            | either     | 422 `SOURCE_EMPTY`               |
| `rejected/too-many-words.txt`   | transcript | 413 `SOURCE_WORD_LIMIT_EXCEEDED` |

A file over the 512 KiB size limit (413 `SOURCE_TOO_LARGE`) is too big to keep in the
repository. Create one in the git-ignored `var/` folder:

```sh
mkdir -p var && head -c 600000 /dev/zero | tr '\0' 'a' > var/oversized.txt
```

## Adding a sample

Keep files synthetic and small, add a row above, and add the file to `SAMPLE_UPLOADS` in
`apps/api/tests/test_sources.py`.
