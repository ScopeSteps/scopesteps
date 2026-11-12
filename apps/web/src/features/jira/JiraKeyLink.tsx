import { cx } from '@/lib/cx';

import type { JiraIssueLink } from './types';

/** An item's Jira issue key, linking to it in Jira while the project is connected. */
export function JiraKeyLink({ link }: { link: JiraIssueLink }) {
  const label = link.closed ? `${link.jira_key} (closed in Jira)` : link.jira_key;
  const classes = 'font-mono text-xs tabular-nums';
  if (!link.url) {
    return (
      <span className={cx(classes, 'text-subtle')} title="Jira is no longer connected">
        {label}
      </span>
    );
  }
  return (
    <a
      className={cx(classes, 'rounded px-1 text-accent-ink underline hover:bg-hover')}
      href={link.url}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open ${link.jira_key} in Jira${link.closed ? ' (closed)' : ''}`}
    >
      {label}
    </a>
  );
}
