# scopesteps-notifications

Telling people that a comment needs them: in the app, and by email if they want
([ADR 0021](../../docs/adr/0021-mentions-followers-and-notifications.md)).

A notification names who, the project, the thread and the comment, never what was written.

## Public interface

Other modules import only `scopesteps.notifications.client`. `notifier(session)` gives
`discussions` `notify` and `withdraw`, which join its transaction; who gets told is the caller's
decision. The composition root's job calls `send_due_emails` and `delete_expired_notifications`.
The module reads names through `identity.client`, `projects.client` and `backlog.client`.

## What is where

| Path                           | Contains                                                           |
| ------------------------------ | ------------------------------------------------------------------ |
| `client.py`                    | The published interface                                            |
| `domain/notification.py`       | `Notification`, `EmailSettings`, what is still worth emailing      |
| `application/notifications.py` | Recording, reading, marking read, settings, retention              |
| `application/emails.py`        | Batching, claiming a window, the message, sending with one retry   |
| `infrastructure/orm.py`        | `notifications_notifications`, `_email_settings`, `_email_windows` |
| `infrastructure/repository.py` | Stores, the keyset page and the email queue                        |
| `http/`                        | The routes below                                                   |

## API

| Route                                | Does                                                     |
| ------------------------------------ | -------------------------------------------------------- |
| `GET /me/notifications`              | Yours, newest first; `unread`, `limit` (to 50), `cursor` |
| `GET /me/notifications/unread-count` | `{"unread"}`                                             |
| `POST /me/notifications/{id}/read`   | Marks one read; 404 if it is not yours; 204              |
| `POST /me/notifications/read-all`    | Marks all yours read; 204                                |
| `GET /me/notification-settings`      | `email_on_mention` (true by default), `email_on_reply`   |
| `PUT /me/notification-settings`      | Saves both                                               |

Lists and counts leave out projects you no longer belong to. Reading and saving are naturally
idempotent, so these routes take no `Idempotency-Key`.

## Rules

- **Retention.** Notifications are deleted after 90 days by the daily clean-up.
- **Email.** At most one per person and thread every 15 minutes. What arrives inside a window goes
  out as one batch when it ends, unless it stopped being news.
- **Failures.** One retry, then the email is dropped and logged by kind, with no address.

Tested through the API in `apps/api/tests/test_notifications.py`.
