# scopesteps-sources

Source upload and validation, immutable source versions and source blocks.

## Public interface

Other modules import only `scopesteps.sources.client`. `current_version_ids` gives the agent's
conversation the newest version of each source a project has not removed. Everything else is internal and
enforced by import-linter.

## Layout

| Path              | Contains                                                     |
| ----------------- | ------------------------------------------------------------ |
| `client.py`       | Published IDs and DTOs other modules use                     |
| `domain/`         | Entities, value objects, invariants and events. Pure Python. |
| `application/`    | Use cases and ports (repository/provider protocols)          |
| `infrastructure/` | SQLAlchemy tables and repositories, external adapters        |
| `http/`           | FastAPI router, request/response schemas, dependencies       |

Tables are prefixed `sources_` (ADR 0003).

## API

| Route                                                | Does                                                     |
| ---------------------------------------------------- | -------------------------------------------------------- |
| `POST /projects/{id}/sources`                        | Stores one or more files as new sources, all or none     |
| `POST /projects/{id}/sources/{source_id}/versions`   | Stores corrected content as the source's next version    |
| `DELETE /projects/{id}/sources/{source_id}`          | Removes an unused source from the project's current set  |
| `GET /projects/{id}/sources`                         | Lists the current version of each source not removed     |
| `GET /projects/{id}/sources/{source_version}/blocks` | Lists a version's paragraphs with their IDs and locators |

Uploads are `multipart/form-data` with an `Idempotency-Key` header. On `POST .../sources` each
file part is named by its kind (`brief`, `transcript` or `supporting_document`); send one or more
parts, of one kind or several, up to 20 files. Versions come back in the order brief, transcript,
supporting document, each in the order sent. `POST .../versions` takes one part, `file`. Reading
needs any role on the project; uploading and removing need Editor. A project the actor has no
role in, and a source or version that belongs to another project, are all `404 NOT_FOUND`, so a
response never shows whether they exist.

Each version carries `source_number`: the project's sources are numbered 1, 2, ... in the order
they were added, and a number is never reused, so a client can label a source (`SRC-3`) stably.

| Rejection                                               | Status | `code`                       |
| ------------------------------------------------------- | ------ | ---------------------------- |
| Not `.txt`, `.md` or `.markdown`                        | 415    | `UNSUPPORTED_SOURCE_TYPE`    |
| A file over `SOURCE_MAX_BYTES`                          | 413    | `SOURCE_TOO_LARGE`           |
| Current sources plus the upload over `SOURCE_MAX_WORDS` | 413    | `SOURCE_WORD_LIMIT_EXCEEDED` |
| Not UTF-8, or contains control characters               | 422    | `SOURCE_UNREADABLE`          |
| No text                                                 | 422    | `SOURCE_EMPTY`               |
| No file parts                                           | 422    | `SOURCE_FILES_MISSING`       |
| More than 20 files                                      | 422    | `TOO_MANY_SOURCE_FILES`      |
| A new version of a removed source                       | 409    | `SOURCE_REMOVED`             |
| Removing a source something refers to                   | 409    | `SOURCE_IN_USE`              |
| Key reused with different files                         | 409    | `IDEMPOTENCY_KEY_REUSED`     |
| A concurrent upload finished first                      | 409    | `UPLOAD_IN_PROGRESS`         |
| A concurrent removal finished first                     | 409    | `SOURCE_CHANGED`             |

A file rejection names the file in `details.field` (its kind) and `details.filename`. The word
limit's `details` hold `word_count` (what the project would hold), `current_word_count` and
`max_words`. `SOURCE_IN_USE` has `details.used_by`, counts by kind, for example
`{"run": 1, "backlog_version": 1, "person": 2}`. Error bodies never contain document text.

Sample files for trying this by hand are in [samples/sources](../../samples/sources/README.md).

## Rules

The decisions behind these rules are in
[ADR 0009](../../docs/adr/0009-sources-of-any-kind-and-soft-removal.md).

- Every uploaded file becomes a new source of the kind its part names; a project may hold any
  number of sources of each kind. An upload stores all of its files or none.
- A file identical to the current version of one of the project's current sources, or to an
  earlier file of the same upload, returns that version instead of storing it again.
- A source's content lives in numbered, immutable versions. Corrected content becomes the next
  version through `POST .../versions`, and earlier versions stay readable, so existing citations
  keep resolving.
- The word limit counts the current versions of the project's sources that are not removed, plus
  the upload; a new version counts in place of the one it replaces.
- Removal is soft: the source leaves the current list, the word limit and duplicate matching, and
  runs can no longer pin its versions, but its versions and blocks stay stored and readable by
  id. It is refused while a run pinned, a backlog version was made from or cites, or a person's
  evidence quotes any of its versions. Conversation replies do not count: they only read, and
  their citations stay readable by id (ADR 0010). `sources` asks those modules through the
  `SourceUsageReader` dependency in `client.py`, which the composition root binds
  (`apps/api/src/scopesteps/api/source_usage.py`). Removing a removed source returns it unchanged.
- A version's paragraphs are split by `split_into_blocks` and stored once with their own IDs.
  The locator is the paragraph number plus character offsets into the stored text, which is the
  uploaded text with line endings normalized to LF and any byte-order mark removed.
- The file extension decides the media type. The client's filename is reduced to a display name
  and is never used as a path.
- Repeating a command with the same `Idempotency-Key` and the same files returns the original
  versions. Removal is idempotent by state: the key is required but no receipt is kept.
- Each version a command creates is recorded as a `source.added` audit event, and each removal as
  `source.removed`, in the command's transaction through `audit.client`. A retry, unchanged
  content and a repeated removal record nothing.

## Deviations from the POC plan

- The plan's `POST` took a `files` list; it takes parts named by kind, so each file's kind is
  explicit and the contract lists the kinds.
- The plan's `POST` returned blocks; it returns version metadata, and blocks are read with the
  `GET` route.
- `GET /projects/{id}/sources` is new: the browser needs it to restore the view after a refresh.
- The size limit is applied to each file after the multipart body is received. Nothing in the
  API caps the whole request body yet; a hosted deployment must do that at the proxy.
