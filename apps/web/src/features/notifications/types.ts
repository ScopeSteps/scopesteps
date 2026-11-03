import type { components } from '@scopesteps/api-client';

type Schemas = components['schemas'];
export type Notification = Schemas['NotificationResponse'];
export type NotificationSettings = Schemas['NotificationSettings'];

export const NOTIFICATIONS_KEY = ['notifications'] as const;

/** How often the bell looks for news while the tab is visible; live push is out of scope. */
export const CHECK_EVERY_MS = 30_000;

/** The sentence a notification reads as, without when. */
export function describeNotification(notification: Notification): string {
  const verb = notification.kind === 'mentioned' ? 'mentioned you on' : 'replied on';
  const about = notification.item?.title ?? 'General discussion';
  return `${notification.actor_name} ${verb} ${about}`;
}

/** What the badge shows: an exact count up to nine. */
export function badgeText(unread: number): string {
  return unread > 9 ? '9+' : String(unread);
}
