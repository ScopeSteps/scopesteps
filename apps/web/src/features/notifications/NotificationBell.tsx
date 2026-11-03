import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { useLayer } from '@/components/useLayer';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';
import { formatRelative, formatWhen } from '@/lib/formatWhen';

import { badgeText, describeNotification } from './types';
import type { Notification } from './types';
import { useNotificationCommands, useNotificationList, useUnreadCount } from './useNotifications';

interface NotificationBellProps {
  /** Where a notification leads: its thread, with the comment highlighted. */
  commentHref: (notification: Notification) => string;
}

function bellLabel(unread: number): string {
  if (unread === 0) {
    return 'Notifications';
  }
  return unread === 1 ? '1 unread notification' : `${String(unread)} unread notifications`;
}

/** The bell in the top bar, with the number of unread notifications and the list behind it. */
export function NotificationBell({ commentHref }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const { data: unread = 0 } = useUnreadCount();

  return (
    <div className="relative flex-none">
      <button
        ref={button}
        type="button"
        aria-label={bellLabel(unread)}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          setOpen((current) => !current);
        }}
        className="relative flex size-8 cursor-pointer items-center justify-center rounded-lg text-muted hover:bg-hover hover:text-fg focus-visible:shadow-focus focus-visible:outline-none"
      >
        <Icon name="bell" size={18} />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 font-mono text-[10px] font-semibold text-accent-fg tabular-nums"
          >
            {badgeText(unread)}
          </span>
        )}
      </button>
      {open && (
        <NotificationList
          trigger={button}
          unread={unread}
          commentHref={commentHref}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </div>
  );
}

interface NotificationListProps extends NotificationBellProps {
  trigger: React.RefObject<HTMLElement | null>;
  unread: number;
  onClose: () => void;
}

function NotificationList({ trigger, unread, commentHref, onClose }: NotificationListProps) {
  const panel = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const list = useNotificationList(true);
  const { read, readAll } = useNotificationCommands();
  useLayer(panel, { onClose, returnFocus: trigger, trapFocus: false });

  function open(notification: Notification) {
    if (notification.read_at === null) {
      read.mutate(notification.id);
    }
    onClose();
    void navigate(commentHref(notification));
  }

  return (
    <div
      ref={panel}
      role="dialog"
      aria-label="Notifications"
      tabIndex={-1}
      onBlur={(event) => {
        // A click elsewhere closes it; moving through its items does not.
        if (
          event.relatedTarget !== null &&
          !event.currentTarget.contains(event.relatedTarget) &&
          event.relatedTarget !== trigger.current
        ) {
          onClose();
        }
      }}
      className="absolute top-full right-0 z-[25] mt-1.5 flex max-h-[min(480px,calc(100vh-72px))] w-[min(380px,calc(100vw-24px))] flex-col rounded-xl border border-line bg-surface shadow-pop focus:outline-none"
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <strong className="text-sm font-semibold">Notifications</strong>
        <Button
          size="sm"
          variant="ghost"
          disabled={unread === 0 || readAll.isPending}
          onClick={() => {
            readAll.mutate();
          }}
        >
          Mark all as read
        </Button>
      </div>
      <div className="flex min-h-0 flex-col overflow-auto p-1.5">
        {list.isPending ? (
          <p role="status" className="p-3 text-sm text-subtle">
            Loading notifications…
          </p>
        ) : list.error ? (
          <Banner tone="bad" role="alert">
            Could not load your notifications. {describeError(list.error)}
          </Banner>
        ) : list.data.length === 0 ? (
          <p className="p-3 text-center text-sm text-muted">You’re all caught up</p>
        ) : (
          <ul className="m-0 flex list-none flex-col p-0">
            {list.data.map((notification) => (
              <li key={notification.id}>
                <button
                  type="button"
                  onClick={() => {
                    open(notification);
                  }}
                  className={cx(
                    'flex w-full cursor-pointer flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left text-[13px] hover:bg-hover focus-visible:shadow-focus focus-visible:outline-none',
                    notification.read_at === null ? 'font-semibold text-fg' : 'text-muted',
                  )}
                >
                  <span className="break-words">{describeNotification(notification)}</span>
                  <span className="text-xs font-normal text-subtle">
                    {notification.project_name} ·{' '}
                    <time
                      dateTime={notification.created_at}
                      title={formatWhen(notification.created_at)}
                    >
                      {formatRelative(notification.created_at)}
                    </time>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
