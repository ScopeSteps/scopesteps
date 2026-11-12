import type { JiraConnection } from './types';

const DAY = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' });

/** A calendar day from the API (yyyy-mm-dd) in the reader's locale, "Mar 1, 2027", on any time zone. */
export function formatDay(day: string): string {
  return DAY.format(new Date(`${day}T00:00:00Z`));
}

export interface TokenMessage {
  tone: 'warn' | 'bad';
  text: string;
  /** Publishing is stopped until an Approver connects again with a new token. */
  stopped: boolean;
}

/** What to tell the team about the Jira API token; null while it works and is not near expiry. */
export function tokenMessage(connection: JiraConnection): TokenMessage | null {
  const expires = connection.token_expires_on;
  switch (connection.token_state) {
    case 'working':
      return null;
    case 'expires_soon': {
      const days = connection.token_days_left ?? 0;
      const when = days <= 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${String(days)} days`;
      return {
        tone: 'warn',
        text: `The Jira API token expires ${when}${expires ? ` (${formatDay(expires)})` : ''}. Make a new token and reconnect before then, or publishing to Jira stops.`,
        stopped: false,
      };
    }
    case 'expired':
      return {
        tone: 'bad',
        text: `The Jira API token expired${expires ? ` on ${formatDay(expires)}` : ''}, so publishing to Jira is stopped. Reconnect with a new token to start again.`,
        stopped: true,
      };
    case 'rejected':
      return {
        tone: 'bad',
        text: 'Jira no longer accepts the API token, so publishing to Jira is stopped. It may have been revoked, or the account removed. Reconnect with a new token to start again.',
        stopped: true,
      };
  }
}
