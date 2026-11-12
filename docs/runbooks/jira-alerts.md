# Jira alerts runbook

What the Jira publishing alert means, how to check it and what to do. The rule is in
[ops/monitoring/alerts.yaml](../../ops/monitoring/alerts.yaml) (group `scopesteps-jira`), the
way agent alerts are ([ADR 0023](../adr/0023-alert-rules-as-code-from-evaluation-results.md)).
Publishing itself is [ADR 0029](../adr/0029-one-way-jira-publishing-through-an-outbox.md).

Alerts show up where agent alerts do: the local inbox at http://localhost:8025 and Prometheus at
http://localhost:9090/alerts (see the [agent alerts runbook](agent-alerts.md), "Where alerts
show up"). The API exports only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

## The metrics

Each API process reads the publish table every time it exports (once a minute), so the figures
are the same whichever process or worker sent the publishes. Counts and an age only: no project,
version, item or person.

| Metric in Prometheus                                                  | What it is                                                  |
| --------------------------------------------------------------------- | ----------------------------------------------------------- |
| `scopesteps_jira_publish_oldest_sending_age_seconds`                  | How long the oldest publish still sending has been at it; 0 |
| `scopesteps_jira_publishes_sending`                                   | Publishes still sending                                     |
| `scopesteps_jira_publishes_finished_total{scopesteps_publish_status}` | Publishes that ended, `done` or `failed`                    |

## JiraPublishStuck

**What it means.** A publish has been sending for more than 30 minutes. A publish normally ends
within a minute, and the background sender waits at most 15 minutes between attempts when Jira
asks it to slow down or cannot be reached, so 30 minutes is two waits without an end. The
approver sees "Publishing to Jira: N of M sent" and nothing moves.

**What to check, in this order.**

1. **Is the background sender running?** In the API log, look for `Jira publish job failed`
   (an error in a round) and check `JIRA_PUBLISH_WORKER`. With `separate`, the API sends nothing
   in the background and `scopesteps-jira-worker` must be running; with `in_process` (the
   default), the API process itself sends every `JIRA_PUBLISH_INTERVAL_SECONDS`. A host that puts
   the API to sleep stops it too.
2. **Is Jira reachable?** Check https://status.atlassian.com for the project's site. The publish
   in `GET /api/v1/jira/publishes/{id}` shows `last_error` (`JIRA_UNAVAILABLE` or
   `JIRA_RATE_LIMITED`) and `next_attempt_at`; it carries on by itself once Jira answers.
3. **Is the token still accepted?** `GET /api/v1/projects/{id}/jira/connection` shows
   `token_state`. `rejected` or `expired` stops publishing: an Approver reconnects Jira with a
   new token in Project settings, then presses Retry. The approvers were told by notification
   and email when this happened.
4. **Did a sender die mid-round?** A publish is held under a five-minute lease; if the process
   holding it stopped, the lease runs out and the next round takes the publish over. An item
   sent five times without an answer fails on its own, so one item cannot hold a publish forever.

**What to do.** Fix the cause above. Nothing needs to be cleaned up: the outbox remembers what
was sent, so when the sender runs again the publish continues without duplicates (ADR 0029).
The alert clears by itself once the publish ends.
