import type { ReactNode } from 'react';

import { Banner } from '@/components/Banner';

import { tokenMessage } from './tokenState';
import type { JiraConnection } from './types';

interface TokenStateBannerProps {
  connection: JiraConnection;
  /** A Reconnect button, for someone who may connect Jira. */
  action?: ReactNode;
  /** Added for someone who cannot fix it themselves. */
  askApprover?: boolean;
}

/** A warning when the Jira API token expires soon, expired or was refused; nothing otherwise. */
export function TokenStateBanner({
  connection,
  action,
  askApprover = false,
}: TokenStateBannerProps) {
  const message = tokenMessage(connection);
  if (!message) {
    return null;
  }
  return (
    <Banner tone={message.tone} role={message.stopped ? 'alert' : 'status'} action={action}>
      {message.text}
      {askApprover && ' Ask an Approver to reconnect.'}
    </Banner>
  );
}
