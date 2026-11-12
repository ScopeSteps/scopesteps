import { useId, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { describeError } from '@/lib/apiError';

import { JIRA_SETUP_GUIDE } from './types';
import type { JiraConnection } from './types';
import { useJiraConnectionCommands } from './useJiraCommands';

interface JiraConnectFormProps {
  projectId: string;
  /** The current connection when reconnecting: its address, email and project are filled in. */
  current: JiraConnection | null;
  onDone: () => void;
  onCancel: () => void;
}

type Field = 'siteUrl' | 'email' | 'apiToken' | 'projectKey';

const REQUIRED: Record<Field, string> = {
  siteUrl: 'Enter your Jira address.',
  email: 'Enter the Jira account’s email.',
  apiToken: 'Paste an API token of that account.',
  projectKey: 'Enter the Jira project key.',
};

/**
 * Connect Jira: the server tests the address, account, token and project before saving
 * anything. The token goes to the server once and is never shown again.
 */
export function JiraConnectForm({ projectId, current, onDone, onCancel }: JiraConnectFormProps) {
  const { connect } = useJiraConnectionCommands(projectId);
  const formId = useId();
  const [values, setValues] = useState<Record<Field, string>>({
    siteUrl: current?.site_url ?? '',
    email: current?.email ?? '',
    apiToken: '',
    projectKey: current?.jira_project_key ?? '',
  });
  const [expiresOn, setExpiresOn] = useState(current?.token_expires_on ?? '');
  const [missing, setMissing] = useState<ReadonlySet<Field>>(new Set());

  function set(field: Field, value: string) {
    setValues((before) => ({ ...before, [field]: value }));
    setMissing((before) => {
      const next = new Set(before);
      next.delete(field);
      return next;
    });
    connect.reset();
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (connect.isPending) {
      return;
    }
    const blank = (Object.keys(REQUIRED) as Field[]).filter((field) => values[field].trim() === '');
    if (blank.length > 0) {
      setMissing(new Set(blank));
      return;
    }
    connect.mutate(
      {
        siteUrl: values.siteUrl.trim(),
        email: values.email.trim(),
        apiToken: values.apiToken,
        projectKey: values.projectKey.trim().toUpperCase(),
        tokenExpiresOn: expiresOn === '' ? null : expiresOn,
      },
      {
        onSuccess: () => {
          // The token is not kept in the page once the server has it.
          setValues((before) => ({ ...before, apiToken: '' }));
          onDone();
        },
      },
    );
  }

  const error = (field: Field) => (missing.has(field) ? REQUIRED[field] : null);

  return (
    <form
      id={formId}
      onSubmit={submit}
      noValidate
      autoComplete="off"
      aria-label={current ? 'Reconnect Jira' : 'Connect Jira'}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface-2 p-3"
    >
      <p className="text-xs text-muted">
        Use a separate Jira account, such as “ScopeSteps Bot”, so publishing keeps working when
        people leave the team.{' '}
        <a
          className="text-accent-ink underline"
          href={JIRA_SETUP_GUIDE}
          target="_blank"
          rel="noreferrer"
        >
          How to set it up
        </a>
      </p>
      <TextField
        label="Jira address"
        value={values.siteUrl}
        placeholder="your-team.atlassian.net"
        onChange={(value) => {
          set('siteUrl', value);
        }}
        help="Jira Cloud only."
        error={error('siteUrl')}
      />
      <TextField
        label="Jira account email"
        type="email"
        value={values.email}
        onChange={(value) => {
          set('email', value);
        }}
        error={error('email')}
      />
      <TextField
        label="API token"
        type="password"
        value={values.apiToken}
        autoComplete="new-password"
        onChange={(value) => {
          set('apiToken', value);
        }}
        help="Make one in your Atlassian account under Security, API tokens. It is stored encrypted and never shown again."
        error={error('apiToken')}
      />
      <TextField
        label="Jira project key"
        value={values.projectKey}
        placeholder="WEB"
        maxLength={10}
        onChange={(value) => {
          set('projectKey', value);
        }}
        help="The letters before each issue number, like WEB in WEB-12."
        error={error('projectKey')}
      />
      <TextField
        label="Token expires on (optional)"
        type="date"
        value={expiresOn}
        onChange={(value) => {
          setExpiresOn(value);
          connect.reset();
        }}
        help="The date Atlassian showed when you made the token. You get a warning 14 days before."
      />
      {connect.error && (
        <Banner tone="bad" role="alert">
          Jira was not connected. {describeError(connect.error)}
        </Banner>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button onClick={onCancel} disabled={connect.isPending}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={connect.isPending}>
          {connect.isPending ? 'Checking with Jira…' : current ? 'Reconnect' : 'Connect'}
        </Button>
      </div>
    </form>
  );
}
