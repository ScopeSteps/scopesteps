import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];
export type Notification = Schemas['NotificationResponse'];
export type NotificationSettings = Schemas['NotificationSettings'];

export const NOTIFICATIONS_KEY = ['notifications'] as const;

/** How often the bell looks for news while the tab is visible; live push is out of scope. */
export const CHECK_EVERY_MS = 30_000;

/** The counts a publish reports, without the ones that are zero. */
function publishCounts(details: Notification['details'], withFailed: boolean): string {
  const parts = [
    ['created', details?.created ?? 0],
    ['updated', details?.updated ?? 0],
    ['closed', details?.closed ?? 0],
    ...(withFailed ? [['failed', details?.failed ?? 0] as const] : []),
  ] as const;
  const shown = parts.filter(([, count]) => count > 0);
  return shown.map(([label, count]) => `${String(count)} ${label}`).join(', ');
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
    case 'jira_published': {
      const counts = publishCounts(details, false);
      return counts === ''
        ? 'Published to Jira: nothing needed changing'
        : `Published to Jira: ${counts}`;
    }
    case 'jira_publish_failed':
      return `Published to Jira: ${publishCounts(details, true)}. Open to see what failed and retry`;
    case 'jira_token_expiring': {
      const days = details?.days_left ?? 0;
      return `The Jira API token expires ${days <= 0 ? 'today' : days === 1 ? 'tomorrow' : `in ${String(days)} days`}. Reconnect Jira before then`;
    }
    case 'jira_token_stopped':
      return 'Publishing to Jira has stopped: reconnect Jira with a new token';
  }
}

/** Whether a notification is about the project's Jira token, which an approver renews. */
export function isTokenNotice(notification: Notification): boolean {
  return notification.kind === 'jira_token_expiring' || notification.kind === 'jira_token_stopped';
}

export type NotificationTone = 'accent' | 'ok' | 'warn' | 'bad';

/**
 * The icon and status colour of a notification: a discussion for people, ok for a publish that
 * went through, bad for one with failures or a stopped token, warn for a token that runs out soon.
 */
export function notificationLook(notification: Notification): {
  icon: 'discussion' | 'check' | 'warn';
  tone: NotificationTone;
} {
  switch (notification.kind) {
    case 'mentioned':
    case 'replied':
      return { icon: 'discussion', tone: 'accent' };
    case 'jira_published':
      return { icon: 'check', tone: 'ok' };
    case 'jira_publish_failed':
    case 'jira_token_stopped':
      return { icon: 'warn', tone: 'bad' };
    case 'jira_token_expiring':
      return { icon: 'warn', tone: 'warn' };
  }
}

/** What the badge shows: an exact count up to nine. */
export function badgeText(unread: number): string {
  return unread > 9 ? '9+' : String(unread);
}
