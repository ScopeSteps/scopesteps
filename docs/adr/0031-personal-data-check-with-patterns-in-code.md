# 0031. Check backlogs for personal data with patterns in code

- Status: Proposed
- Date: 2026-11-13

## Context

Real meetings hold small talk and personal remarks: sport, a colleague's sick leave, a customer's
address. A backlog must not repeat them (SSPOC-151). Sara decided on 2026-11-03 to handle this in
three layers now: measure leaks in every evaluation, tell the agent in its prompts, and check in
code before approval. Microsoft Presidio, an open-source detector, was named as one option for
the code check.

Presidio finds names, places and more with spaCy language models. Those models add hundreds of
megabytes to the API image, slow its start, and flag every person's name, which a backlog
legitimately holds ("Dana approves bookings"). The hosting plan is a small instance (ADR 0030,
proposed) and the budget is tight.

## Decision

The code check uses regular expressions in `backlog/domain/privacy.py` for what a pattern can
find reliably: email addresses, phone numbers, payment card numbers (with a Luhn check) and long
account or ID numbers. It reads what approval would keep: titles, descriptions, criteria, the
quotes criteria cite and tasks. A flag never changes the backlog; a person edits the value out,
or an approver keeps it on purpose (audited), and the approval check `personal_data_settled`
refuses approval (409 `APPROVAL_BLOCKED`) until every flag is one or the other.

Remarks about someone's health, pay or job cannot be told from requirements by a pattern. They
are covered by the prompt rule (`draft-v16`, `change-v9`, `reply-v6`, `reply-v7`, adopted only
after measurement) and measured by the evaluations' `off_topic` and `sensitive` passages.

## Consequences

- No new dependency, no model download, and the check runs in microseconds on every read.
- Names and addresses written in words are not flagged. If measurement shows such leaks get past
  the prompt rule, Presidio (or a model-based check) can be added behind the same flags.
- Passages marked sensitive at upload (SSPOC-159/160) can later flag items that cite them through
  the same flags and the same "keep anyway".
