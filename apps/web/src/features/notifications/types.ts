import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];
export type Notification = Schemas['NotificationResponse'];
export type NotificationSettings = Schemas['NotificationSettings'];

export const NOTIFICATIONS_KEY = ['notifications'] as const;

/** How often the bell looks for news while the tab is visible; live push is out of scope. */
export const CHECK_EVERY_MS = 30_000;

function plural(count: number, one: string, many = `${one}s`): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

/** The sentence a notification reads as, without when. Jira ones carry counts only. */
export function describeNotification(notification: Notification): string {
  const details = notification.details;
  switch (notification.kind) {
    case 'mentioned':
    case 'replied': {
      const verb = notification.kind === 'mentioned' ? 'mentioned you on' : 'replied on';
      const about = notification.item?.title ?? 'General discussion';
      return `${notification.actor_name} ${verb} ${about}`;
    }
    case 'jira_published':
      return `Published to Jira: ${String(details?.created ?? 0)} created, ${String(details?.updated ?? 0)} updated, ${String(details?.closed ?? 0)} closed`;
    case 'jira_publish_failed':
      return `${plural(details?.failed ?? 0, 'item')} did not reach Jira. Open to retry`;
    case 'jira_token_expiring': {
      const days = details?.days_left ?? 0;
      return `The Jira API token expires ${days <= 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${String(days)} days`}. Reconnect Jira before then`;
    }
    case 'jira_token_stopped':
      return 'Publishing to Jira has stopped: reconnect Jira with a new token';
  }
}

/** What the badge shows: an exact count up to nine. */
export function badgeText(unread: number): string {
  return unread > 9 ? '9+' : String(unread);
}
