# 0030. Host on Render, with its managed Postgres and a custom domain

- Status: Proposed (awaiting Sara's approval)
- Date: 2026-11-11

## Context

ScopeSteps runs only on a laptop today: SQLite locally, with Postgres in `compose.yaml` for
development. For the demo on 2026-12-03 it must run online for Sara, Dr. Palese and a few
invited test users, with the laptop as a backup. Sara set the budget on 2026-11-03: about $15 to
$40 a month for hosting, the database and email, not counting the AI model.

What the app needs from a host:

- **An always-on API process.** The API runs two background threads: the notification job
  (emails) and the Jira publish sender ([ADR 0029](0029-one-way-jira-publishing-through-an-outbox.md)).
  A free plan that sleeps after 15 idle minutes would stop both, so free web plans are out.
- **Managed Postgres with daily backups.** Approved versions are the record of what was agreed
  and must survive a mistake or a lost disk.
- **HTTPS on our own domain**, secrets kept out of git (`JIRA_TOKEN_KEY`, the model key, the
  email key, the session secret), and deploys from GitHub that can be rolled back.
- **Small scale**: a handful of users, one API process, a database well under 1 GB.

Compared on 2026-11-11 (prices from the hosts' pages where reachable, otherwise from recent
third-party summaries; they are checked again on the host's own pricing page before signing up,
in SSPOC-166):

|                             | Render                                                                      | Railway                                                                    | Fly.io                                                         |
| --------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| API (always on)             | Starter web service, 512 MB: **$7**                                         | Usage-billed: about $5 to $10 for 0.5 GB RAM always on, inside the $5 plan | shared-cpu-1x, 512 MB: **$3.69**                               |
| Web app (static files)      | Static site: **$0**                                                         | Served by a service: a few dollars of usage                                | Served by the API machine: $0                                  |
| Managed Postgres            | Basic-256 MB **$6**, or Basic-1 GB **$19**; storage $0.30/GB                | No separate price: billed as usage, about $6 to $20 small                  | Managed Postgres Basic, 1 GB: **$38**; storage $0.28/GB        |
| Backups                     | Point-in-time recovery, 3 days on the Hobby workspace (7 on Pro); exports   | Volume backups (retention to confirm)                                      | Included with Managed Postgres                                 |
| HTTPS on a custom domain    | Yes, certificates included                                                  | Yes                                                                        | Yes                                                            |
| Secrets                     | Environment variables and groups, secret files                              | Variables per service                                                      | `fly secrets`                                                  |
| Deploys and rollbacks       | Auto-deploy on push to `main`; roll back to any earlier deploy in one click | Deploy on push; roll back to an earlier deploy                             | `fly deploy` from CI; roll back by deploying the earlier image |
| Regions                     | Oregon, Ohio, Virginia, Frankfurt, Singapore                                | US, EU, Asia                                                               | Many                                                           |
| **Monthly total, our size** | **about $15** (Basic-256 MB) **to $28** (Basic-1 GB)                        | **about $15 to $25**, varies with use                                      | **about $44**: over budget                                     |

The totals include email and the domain (below). Fly.io is over budget because of its managed
Postgres price; running Postgres ourselves on a Fly machine would be cheaper but is not managed,
so backups and upgrades would be ours. Railway fits the budget but bills by usage, so the monthly
cost moves with use and is harder to promise in advance.

Email: [Resend](https://resend.com) free plan, 3,000 emails a month and 100 a day, one verified
domain: **$0** at our size (invitations, mentions, Jira publish notices).

## Decision

- **Host on Render**, in one region close to the users (US East, Virginia or Ohio, unless Sara
  prefers Frankfurt):
  - the API as a **Starter web service** ($7), always on, built from a Dockerfile;
  - the web app as a **static site** ($0), calling the API on the same domain;
  - **Render Postgres Basic-256 MB** ($6, plus about $0.30 storage), moving to Basic-1 GB ($19)
    only if memory runs short. Point-in-time recovery covers the last 3 days, and a nightly
    logical export is kept as well.
- **Use a custom domain** (about $12 a year, $1 a month), not the host's `onrender.com`
  subdomain: email services need a verified domain we own (SPF and DKIM records) to deliver
  reliably, and the address stays the same if the host ever changes.
- **Send email through Resend's free plan.**
- **Estimated monthly total: about $15** ($7 API + $6.30 database + $0 email + $1 domain), and
  about $28 with the larger database; both within $15 to $40.
- **The AI model is costed separately.** Today it is Gemini's free tier ($0), which may use the
  data it receives; the model comparison (SSPOC-144) will price a paid model and record it in
  its own ADR, and the site-wide spending cap (SSPOC-170) bounds it.

## Consequences

- SSPOC-166 adds a Dockerfile for the API, Render's settings as code (`render.yaml`), and runs the
  migrations against Postgres on deploy. The Jira sender and notification job keep running in
  the API process; Postgres replaces SQLite online.
- SSPOC-167 turns on auto-deploy from `main` and a test site; rollbacks use Render's earlier
  deploys. SSPOC-168 verifies the domain with Resend.
- Secrets live only in Render's environment settings, never in `render.yaml` or git.
- One Starter instance is a single point of failure; the laptop stays the demo backup.
- If usage grows, the next steps up are the 1 GB database ($19) and the Standard web service
  ($25), still about $45 a month.
