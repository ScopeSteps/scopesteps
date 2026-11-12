import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Select } from '@/components/Select';
import { useToast } from '@/components/toastContext';
import { ApiError, describeError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

import { JiraConnectForm } from './JiraConnectForm';
import { formatDay, tokenMessage } from './tokenState';
import { TokenStateBanner } from './TokenStateBanner';
import type { JiraConnection, Publishers } from './types';
import { useJiraConnectionCommands } from './useJiraCommands';
import { useJiraConnection } from './useJiraConnection';

const PUBLISHER_CHOICES: { value: Publishers; label: string }[] = [
  { value: 'approvers', label: 'Approvers only' },
  { value: 'approvers_and_editors', label: 'Approvers and Editors' },
];

function Heading() {
  return (
    <div className="flex flex-col gap-0.5">
      <h3 className="text-[13px] font-semibold">Jira</h3>
      <p className="text-xs text-subtle">
        Send approved versions to a Jira Cloud project: epics, stories and their tasks. Later
        versions update the same issues; nothing in Jira is deleted.
      </p>
    </div>
  );
}

/** The project's Jira connection in Project settings. Only an Approver connects or changes it. */
export function JiraSettings({ projectId }: { projectId: string }) {
  const { data: status, error, refetch } = useJiraConnection(projectId);
  const [connecting, setConnecting] = useState(false);
  const showToast = useToast();

  let body;
  if (!status) {
    body = error ? (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the Jira connection. {describeError(error)}
      </Banner>
    ) : (
      <p role="status" className="text-xs text-subtle">
        Loading the Jira connection…
      </p>
    );
  } else if (!status.configured) {
    body = (
      <p className="text-xs text-subtle">
        This ScopeSteps server is not set up to connect to Jira yet.
      </p>
    );
  } else if (connecting && status.can_manage) {
    body = (
      <JiraConnectForm
        projectId={projectId}
        current={status.connection}
        onDone={() => {
          setConnecting(false);
          showToast('Jira connected. The details worked.');
        }}
        onCancel={() => {
          setConnecting(false);
        }}
      />
    );
  } else if (!status.connection) {
    body = status.can_manage ? (
      <div>
        <Button
          onClick={() => {
            setConnecting(true);
          }}
        >
          Connect Jira
        </Button>
      </div>
    ) : (
      <p className="text-xs text-subtle">Not connected. An Approver can connect Jira.</p>
    );
  } else {
    body = (
      <ConnectionDetails
        projectId={projectId}
        connection={status.connection}
        canManage={status.can_manage}
        onReconnect={() => {
          setConnecting(true);
        }}
      />
    );
  }

  return (
    <section aria-label="Jira" className="flex flex-col gap-2.5 border-t border-line pt-3.5">
      <Heading />
      {body}
    </section>
  );
}

interface ConnectionDetailsProps {
  projectId: string;
  connection: JiraConnection;
  canManage: boolean;
  onReconnect: () => void;
}

function ConnectionDetails({
  projectId,
  connection,
  canManage,
  onReconnect,
}: ConnectionDetailsProps) {
  const { test, change, disconnect } = useJiraConnectionCommands(projectId);
  const [confirming, setConfirming] = useState(false);
  const showToast = useToast();
  const stopped = tokenMessage(connection)?.stopped === true;
  const busy = test.isPending || change.isPending || disconnect.isPending;
  const changed =
    change.error instanceof ApiError && change.error.code === 'CONNECTION_CHANGED'
      ? change.error
      : null;

  return (
    <div className="flex flex-col gap-2.5">
      <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
        <dt className="text-subtle">Jira project</dt>
        <dd className="m-0 break-words">
          <a
            className="text-accent-ink underline"
            href={`${connection.site_url}/browse/${connection.jira_project_key}`}
            target="_blank"
            rel="noreferrer"
          >
            {connection.jira_project_name}
          </a>{' '}
          <span className="font-mono text-xs text-subtle">{connection.jira_project_key}</span>
        </dd>
        <dt className="text-subtle">Connected as</dt>
        <dd className="m-0 break-words">
          {connection.jira_account_name}
          {connection.email && <span className="text-subtle"> ({connection.email})</span>}
        </dd>
        {connection.token_expires_on && (
          <>
            <dt className="text-subtle">Token expires</dt>
            <dd className="m-0">{formatDay(connection.token_expires_on)}</dd>
          </>
        )}
        <dt className="text-subtle">Last worked</dt>
        <dd className="m-0">{formatWhen(connection.checked_at)}</dd>
      </dl>
      <TokenStateBanner
        connection={connection}
        askApprover={!canManage}
        action={
          canManage ? (
            <Button size="sm" variant={stopped ? 'primary' : 'default'} onClick={onReconnect}>
              Reconnect
            </Button>
          ) : undefined
        }
      />
      {canManage && (
        <>
          <label className="flex cursor-pointer items-start gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={connection.auto_publish}
              disabled={busy}
              onChange={(event) => {
                change.mutate({
                  autoPublish: event.target.checked,
                  expectedRevision: connection.revision,
                });
              }}
              className="mt-0.5 size-4 accent-[var(--accent)]"
            />
            <span className="flex flex-col">
              <span>Publish approved versions to Jira automatically</span>
              <span className="text-xs text-subtle">
                Off: someone publishes each version with “Publish to Jira”. On: every newly approved
                version is sent without asking.
              </span>
            </span>
          </label>
          <div className="flex flex-col gap-1">
            <label htmlFor={`${projectId}-publishers`} className="text-[13px]">
              Who can publish to Jira
            </label>
            <Select
              id={`${projectId}-publishers`}
              value={connection.publishers}
              disabled={busy}
              onChange={(event) => {
                const picked = PUBLISHER_CHOICES.find(
                  (choice) => choice.value === event.target.value,
                );
                if (picked) {
                  change.mutate({
                    publishers: picked.value,
                    expectedRevision: connection.revision,
                  });
                }
              }}
            >
              {PUBLISHER_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </Select>
            <span className="text-xs text-subtle">
              Connecting Jira and these settings stay with Approvers.
            </span>
          </div>
          {changed && (
            <Banner tone="warn" role="alert">
              Someone else changed the Jira settings meanwhile. What you see now is the latest;
              change it again if you still need to.
            </Banner>
          )}
          {change.error && !changed && (
            <Banner tone="bad" role="alert">
              The setting was not saved. {describeError(change.error)}
            </Banner>
          )}
          {test.error && (
            <Banner tone="bad" role="alert">
              The connection test failed. {describeError(test.error)}
            </Banner>
          )}
          {disconnect.error && (
            <Banner tone="bad" role="alert">
              Jira was not disconnected. {describeError(disconnect.error)}
            </Banner>
          )}
          {confirming ? (
            <Banner
              tone="warn"
              role="alert"
              action={
                <span className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      setConfirming(false);
                    }}
                  >
                    Keep it
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={disconnect.isPending}
                    onClick={() => {
                      disconnect.mutate(undefined, {
                        onSuccess: () => {
                          setConfirming(false);
                          showToast('Jira disconnected. Its issues stay in Jira.');
                        },
                      });
                    }}
                  >
                    {disconnect.isPending ? 'Disconnecting…' : 'Yes, disconnect'}
                  </Button>
                </span>
              }
            >
              Disconnect Jira? The saved token is deleted. Issues already in Jira stay there.
            </Banner>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={busy}
                onClick={() => {
                  test.mutate(undefined, {
                    onSuccess: () => {
                      showToast('The Jira connection works.');
                    },
                  });
                }}
              >
                {test.isPending ? 'Testing…' : 'Test connection'}
              </Button>
              {!stopped && (
                <Button size="sm" disabled={busy} onClick={onReconnect}>
                  Change details
                </Button>
              )}
              <Button
                size="sm"
                variant="danger"
                disabled={busy}
                onClick={() => {
                  setConfirming(true);
                }}
              >
                Disconnect
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
