# scopesteps-discussions

Discussion threads on an epic or story, or in the project's General discussion, so scope talk
that happens outside meetings is written down where the whole team can see it
([ADR 0020](../../docs/adr/0020-discussions-as-their-own-module.md)).

A comment is never a decision: nothing here changes the backlog, a scope decision or an approval,
and the agent sees a discussion only as text a person sends in a change request.

## Public interface

Other modules import only `scopesteps.discussions.client`, which publishes `ThreadId` and
`CommentId`, and for a change request `require_thread`, `link_change_request` and
`thread_origins`. Everything else is internal and enforced by import-linter. The module reads item
names and the current backlog version through `backlog.client` (`describe_items`,
`current_version_id`), people through `identity.client` (`UserDirectory`) and request status
through `change_control.client`, tells people through `notifications.client`, and records activity
through `audit.client`.

## What is where

| Path                           | Contains                                                                          |
| ------------------------------ | --------------------------------------------------------------------------------- |
| `client.py`                    | The published ids                                                                 |
| `domain/thread.py`             | `Thread`, `Comment`, the body rule, mentions, the quote, the module's errors      |
| `application/threads.py`       | Every use case, the ports they take, the rate limit, receipts and the list cursor |
| `infrastructure/orm.py`        | Threads, comments, receipts, `_thread_followers` and `_change_requests`           |
| `infrastructure/repository.py` | Revision-checked writes, the keyset page, counts; the adapter over `backlog`      |
| `http/`                        | The routes below                                                                  |

Tables are prefixed `discussions_` (ADR 0003).

## API

| Route                                    | Does                                                      | Needs                        |
| ---------------------------------------- | --------------------------------------------------------- | ---------------------------- |
| `GET /projects/{id}/threads`             | Threads with their comments, newest activity first, paged | Any role                     |
| `GET /projects/{id}/threads/counts`      | Open threads per item, and in General discussion          | Any role                     |
| `POST /projects/{id}/threads`            | Starts a thread with its first comment                    | Any role                     |
| `GET /threads/{thread_id}`               | One thread with its comments                              | Any role                     |
| `POST /threads/{thread_id}/comments`     | Replies at the end of an open thread; returns the thread  | Any role                     |
| `PATCH /comments/{comment_id}`           | Edits a comment's text                                    | Its author                   |
| `DELETE /comments/{comment_id}`          | Deletes a comment (soft); 204                             | Its author                   |
| `POST /threads/{thread_id}/resolve`      | Resolves a thread                                         | Its author, Editor, Approver |
| `POST /threads/{thread_id}/reopen`       | Reopens a resolved thread                                 | Any role                     |
| `PUT /threads/{thread_id}/follow`        | Follows or unfollows, `{"following"}`                     | Any role                     |
| `GET /threads/{id}/change-request-draft` | The thread quoted for a change request                    | Editor, Approver             |

The list takes `item_id` (one item's threads), `general=true` (General discussion only),
`status` (`open`, `resolved` or `all`, the default), `limit` (1 to 50, 20 by default) and
`cursor`, and returns `{"threads": [...], "next_cursor": ...}`. Every command but delete needs an
`Idempotency-Key`; a repeat returns the thread as it is now. `PATCH` takes `{"body",
"expected_revision"}`, resolve and reopen `{"expected_revision"}` (the thread's).

A thread has `item_id` (null for General discussion) and `item` (`kind`, `title`,
`in_current_backlog`, false once the item left the backlog), `status`, `revision`, who created and
who resolved it, `following` for the reader, `change_requests` (`id`, `number`, `status`),
`participants` and `comments`, oldest first. `participants` is everyone who wrote, is mentioned
or follows (`wrote`, `mentioned`, `following`), in the order they first appear in the comments,
then other followers by name, each with their current `display_name`. Someone who left the
project stays listed for what they wrote or were named in, with `left_project` true and
`following` false; deleted comments count for nobody. A comment has its `author_name` as it was when written, `body` (null
once deleted), `mentions` (`user_id`, current `display_name`), `deleted`, `revision`, `edited_at`
and `backlog_version_id`.

| Rejection                                                        | Status | `code`                              |
| ---------------------------------------------------------------- | ------ | ----------------------------------- |
| Body empty after trimming, or over 5,000 characters              | 422    | `COMMENT_EMPTY`, `COMMENT_TOO_LONG` |
| A mention of someone who is not a current member                 | 422    | `MENTION_NOT_MEMBER`                |
| Not a member of the project, or no such thread or comment        | 404    | `NOT_FOUND`                         |
| `item_id` is not an epic or story in the current backlog         | 404    | `ITEM_NOT_FOUND`                    |
| Someone else's comment, or a viewer resolving another's thread   | 403    | `PERMISSION_DENIED`                 |
| Thread's `expected_revision` is stale                            | 409    | `THREAD_CHANGED`                    |
| Comment's `expected_revision` is stale                           | 409    | `COMMENT_CHANGED`                   |
| Replying to a resolved thread                                    | 409    | `THREAD_RESOLVED`                   |
| Key reused for a different request                               | 409    | `IDEMPOTENCY_KEY_REUSED`            |
| More than 30 comments from the member in the project in a minute | 429    | `RATE_LIMITED`                      |

`THREAD_CHANGED` and `COMMENT_CHANGED` carry `details.current_revision`.

## Rules

- **Plain text.** A body is trimmed and stored exactly as written; the web app escapes it and
  links web addresses. Nothing is rendered as HTML.
- **Stable items.** A thread names its item by the id `backlog` keeps across versions, so it stays
  on the item in every version, and stays readable if a later version drops the item. A new
  thread needs the item in the current backlog (the version in flight, or else the baseline).
- **Which version.** Each comment records that same current version when it was written.
- **Deleting.** The text is removed for everyone and the row stays. A deleted reply is left out;
  a deleted first comment shows as "Comment deleted" while replies follow it. A thread with no
  comment left is gone from every list and read.
- **Resolving.** Resolve and reopen are revision-checked. Posting a reply does not move the
  revision, so a reply never makes someone's resolve stale. Resolving a resolved thread, or
  reopening an open one, changes and records nothing.
- **Activity.** `thread.started`, `thread.resolved` and `thread.reopened` are recorded in the
  action's transaction, naming the item ("Started a discussion on story “Book a room”"), never
  the comment text. Refused commands record nothing.
- **Mentions.** A body stores `<@user_id>`. An edit checks only the mentions it adds. See
  [ADR 0021](../../docs/adr/0021-mentions-followers-and-notifications.md) for who is told and who
  follows.
- **The quote.** One paragraph per comment still shown, `<name>, <date>: <text>`, each mention as
  a name and flattened to what a change request accepts. It is capped below the message limit,
  leaving room for what should change; the oldest comments go first, with a note.
- **Names stay.** A comment keeps its author's name, and a resolved thread its resolver's, after
  they leave the project.

Tested through the API in `apps/api/tests/test_discussions.py`, `test_notifications.py` and
`test_change_requests.py`, and the domain rules in `tests/test_thread.py`.
