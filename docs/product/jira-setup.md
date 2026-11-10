# Connecting a project to Jira

ScopeSteps publishes approved backlogs to a Jira Cloud project: epics become Epics, stories
become Stories and tasks become Subtasks under their story. Later versions update the same
issues and close removed ones; nothing in Jira is ever deleted. How it works is in
[ADR 0029](../adr/0029-one-way-jira-publishing-through-an-outbox.md). This page is for the team
setting it up.

Only an **Approver** connects Jira. Everyone on the project uses that one connection; nobody
else needs a Jira token. An Approver also chooses who may publish: Approvers only (the
default), or Approvers and Editors.

## 1. Use a separate Jira account for ScopeSteps (recommended)

ScopeSteps publishes as the Jira account whose API token it is given. Use an account made for
it, for example **ScopeSteps Bot**, not a person's own account:

- Publishing keeps working when someone leaves the team or changes jobs.
- Jira shows "ScopeSteps Bot" as the creator, so it is clear the issue came from ScopeSteps.
  ScopeSteps' activity log still says which person published.
- The account can be given access to the one project it needs, and nothing else.

**Cost:** the account counts as a Jira user. Jira Free covers up to 10 users; on a paid Jira
plan it is billed like any other user. If that is not possible, an Approver's own account
works; it just stops working when that person's account is removed.

To set it up, someone with Jira admin rights:

1. Creates the user, with a shared team mailbox the team can reach (for example
   `scopesteps-bot@your-team.com`), so the token can be renewed when people change.
2. Gives it access to **the one Jira project** ScopeSteps publishes to, and nothing more:
   - In a team-managed project: **Project settings**, **Access**, **Add people**, role
     **Member**.
   - In a company-managed project: a project role with the **Browse projects**, **Create
     issues**, **Edit issues** and **Transition issues** permissions.
   - Never make it a Jira or site administrator.

The Jira project needs the **Epic**, **Story** and **Subtask** issue types. A Scrum or Kanban
software project has them.

## 2. Make an API token

Sign in to Atlassian as the ScopeSteps account, then:

1. Open <https://id.atlassian.com/manage-profile/security/api-tokens> (or your profile picture,
   **Manage account**, **Security**, **Create and manage API tokens**).
2. Click **Create API token**. If you also see "Create API token with scopes", do not choose
   it.
3. Name it "ScopeSteps" and choose when it expires (Atlassian allows up to a year). **Write
   down the expiry date.**
4. Copy the token into your team's password manager. Never paste it into chat, email or a
   ticket.

## 3. Connect in ScopeSteps

As an Approver, open **Project settings**, then **Connect Jira**, and enter:

- the Jira address, like `your-team.atlassian.net`;
- the ScopeSteps account's email and its API token;
- the Jira project key, like `WEB`;
- the token's expiry date.

ScopeSteps checks the details with Jira before saving. It then shows **"Connected as ScopeSteps
Bot"**. The token is stored encrypted and is never shown again, to anyone.

## Check it on a test project (for the ScopeSteps team)

`just jira-check --site your-team.atlassian.net --email bot@your-team.com --project SSTEST`
runs every step publishing takes against a real Jira test project, without the app. It asks
for the API token without showing it, and asks you to type `yes` before it creates a test Epic,
Story and Subtask (named "[ScopeSteps check]"), updates the Story and closes all three. Use a
test project only.

## What ScopeSteps changes in Jira, and what is yours

ScopeSteps is where requirements are decided, so it owns the **summary and description of epics
and stories**: publishing a new approved version rewrites them. Change requirements in
ScopeSteps and publish again; anything typed into those descriptions in Jira is replaced. Put
team notes in Jira **comments**.

A **subtask's description is the team's**: ScopeSteps sets only its summary when a task is
reworded, and never touches the description, so notes written there stay. Status, assignee,
estimates, sprints and comments are never changed by ScopeSteps, except that issues for items
removed from the backlog are moved to Done.

## 4. Keep it working

- **Before the token expires:** ScopeSteps shows a warning 14 days before the date you entered.
  Make a new token (step 2) and connect again with it. Issues published so far stay linked.
- **If Jira stops accepting the token** (it expired early, or someone revoked it): ScopeSteps
  checks every day and when it publishes. It marks the token as not working and stops publishing
  with a plain message. Connect again with a new token, then use **Retry** on any publish that
  stopped.
- **If a token may have leaked:** revoke it on the API tokens page first, then connect again
  with a new one.
- **Moving to another Jira project or site:** connecting to a different project starts fresh
  there. The old project's issues stay in Jira but are no longer updated.
