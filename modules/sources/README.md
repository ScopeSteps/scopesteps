# scopesteps-sources

Source upload and validation, immutable source versions and source blocks.

## Public interface

Other modules import only `scopesteps.sources.client`. Everything else is internal and
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
| `POST /projects/{id}/sources`                        | Stores a brief and a transcript together, or neither     |
| `GET /projects/{id}/sources`                         | Lists the current version of each source                 |
| `GET /projects/{id}/sources/{source_version}/blocks` | Lists a version's paragraphs with their IDs and locators |

Upload is `multipart/form-data` with the file parts `brief` and `transcript` and an
`Idempotency-Key` header. Reading needs any role on the project; uploading needs Editor. A
project the actor has no role in, and a version that belongs to another project, are both
`404 NOT_FOUND`, so a response never shows whether they exist.

| Rejection                                   | Status | `code`                       |
| ------------------------------------------- | ------ | ---------------------------- |
| Not `.txt`, `.md` or `.markdown`            | 415    | `UNSUPPORTED_SOURCE_TYPE`    |
| A file over `SOURCE_MAX_BYTES`              | 413    | `SOURCE_TOO_LARGE`           |
| Both files over `SOURCE_MAX_WORDS` combined | 413    | `SOURCE_WORD_LIMIT_EXCEEDED` |
| Not UTF-8, or contains control characters   | 422    | `SOURCE_UNREADABLE`          |
| No text                                     | 422    | `SOURCE_EMPTY`               |
| Key reused with different files             | 409    | `IDEMPOTENCY_KEY_REUSED`     |
| A concurrent upload finished first          | 409    | `UPLOAD_IN_PROGRESS`         |

`details.field` names the rejected part (`brief` or `transcript`). Error bodies never contain
document text.

## Rules

- A project has one source per kind (brief, transcript). A source's content lives in numbered,
  immutable versions; changed content becomes the next version and earlier versions stay
  readable, so existing citations keep resolving.
- Uploading content identical to a source's current version returns that version.
- A version's paragraphs are split by `split_into_blocks` and stored once with their own IDs.
  The locator is the paragraph number plus character offsets into the stored text, which is the
  uploaded text with line endings normalized to LF and any byte-order mark removed.
- The file extension decides the media type. The client's filename is reduced to a display name
  and is never used as a path.
- Repeating an upload with the same `Idempotency-Key` and the same files returns the original
  versions.

## Deviations from the POC plan

- The plan's `POST` took a `files` list; it now takes the named parts `brief` and `transcript`,
  so each document keeps its identity across versions without relying on its filename.
- The plan's `POST` returned blocks; it returns version metadata, and blocks are read with the
  `GET` route.
- `GET /projects/{id}/sources` is new: the browser needs it to restore the view after a refresh.
- The size limit is applied to each file after the multipart body is received. Nothing in the
  API caps the whole request body yet; a hosted deployment must do that at the proxy.
