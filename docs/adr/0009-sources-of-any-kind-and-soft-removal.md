# 0009. Sources of any kind, explicit new versions and guarded soft removal

- Status: Accepted
- Date: 2026-10-14

## Context

Until now a project had exactly one brief and one transcript, uploaded together. A source's
identity was its kind (`sources_sources` was unique on project and kind), so uploading a new brief
made the next version of the old one. Users need to add any number of documents, of any kind, one
at a time or several at once, and to remove a document that nothing depends on.

Provenance constrains the design. Runs pin source versions, backlog versions are made from and
cite them, and the people a run extracts quote them. Those references live in other modules'
JSON columns, not in foreign keys, so the database cannot stop a delete that would break them.
The activity log names source and version ids as subjects, and upload receipts return stored
versions on a retry.

## Decision

- **One source per uploaded file.** `POST /projects/{id}/sources` takes one or more files whose
  part name is their kind (`brief`, `transcript`, `supporting_document`). Each file becomes a new
  source with version 1 and the project's next `number` (1, 2, ...; never reused), so kind no
  longer identifies a source and a project may have several of each. The upload stores all of its
  files or none.
- **Unchanged content is not stored twice.** A file identical (by SHA-256) to the current version
  of one of the project's sources, or to an earlier file in the same upload, returns that version
  instead of creating a source. A removed source is not matched: re-uploading its content creates
  a new source.
- **A new version is an explicit command.** `POST /projects/{id}/sources/{source_id}/versions`
  stores corrected content as the source's next version. Matching by filename or kind was
  rejected: two meetings can share a file name, and a guess that silently retires a document is
  worse than an extra source.
- **The word limit covers the project's current sources.** An upload is refused when the current
  versions of the sources not removed, plus the new files, exceed `SOURCE_MAX_WORDS`; a new version
  counts in place of the one it replaces.
- **Removal is soft and guarded.** `DELETE /projects/{id}/sources/{source_id}` sets `removed_at`
  and `removed_by` on the source and records `source.removed`. Its versions and blocks are kept
  and stay readable by id; the source leaves the current list, the word limit and dedupe, and a run
  can no longer pin its versions (`409 SOURCE_REMOVED`). Removal is refused with
  `409 SOURCE_IN_USE` while any run pinned, any backlog version was made from or cites, or any
  person's evidence quotes any version of the source; `details.used_by` counts them by kind.
  Removing a removed source returns it unchanged. Nothing is ever deleted.
- **The guard asks the owning modules.** `sources.client` publishes a `SourceUsageReader`
  dependency; the composition root binds it to `agent.client`, `backlog.client` and `projects`,
  which build on `sources` and so cannot be imported by it.

## Consequences

- Stored versions stay immutable and every citation, audit subject and upload receipt keeps
  resolving, whatever is removed.
- Removal frees a project's word allowance but not storage: the text of a removed source stays in
  the database. Deleting content for privacy or retention is a separate decision, to be made with
  a purge that also accounts for audit subjects and receipts.
- Usage is checked by reading the project's runs, backlog versions and people when a removal is
  requested; there is no reference table. That is cheap at POC sizes. A run created at the same
  moment as a removal can pin a version the removal has just checked; the window is one request
  long and the version stays readable, so provenance still holds.
- The existing two-file form keeps working unchanged on the wire, but re-uploading a revised
  brief through it now adds a second brief instead of version 2; the new-version route is the
  way to revise.
- Run prompts stay agnostic to the number of sources: block labels name the kind and, when a run
  pins several versions of one kind, their order ("transcript 2 paragraph 3"), never a filename.
