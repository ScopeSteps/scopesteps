import { useState } from 'react';

import { Button } from '@/components/Button';
import { useToast } from '@/components/toastContext';

import { PublishPreviewModal } from './PublishPreviewModal';
import { tokenMessage } from './tokenState';
import { useJiraConnection } from './useJiraConnection';

interface PublishToJiraProps {
  projectId: string;
  versionId: string;
  versionName: string;
}

/**
 * "Publish to Jira" on an approved version, for someone who may publish once Jira is connected.
 * It opens the preview; while the token is expired or refused it stays visible but disabled.
 */
export function PublishToJira({ projectId, versionId, versionName }: PublishToJiraProps) {
  const { data: status } = useJiraConnection(projectId);
  const [open, setOpen] = useState(false);
  const showToast = useToast();
  const connection = status?.connection;
  if (!connection || !status.can_publish) {
    return null;
  }
  const stopped = tokenMessage(connection)?.stopped === true;
  const reasonId = `jira-stopped-${versionId}`;
  return (
    <>
      <Button
        disabled={stopped}
        aria-describedby={stopped ? reasonId : undefined}
        onClick={() => {
          setOpen(true);
        }}
      >
        Publish to Jira…
      </Button>
      {stopped && (
        <span id={reasonId} className="text-xs text-subtle">
          The Jira token needs renewing in Project settings
        </span>
      )}
      {open && (
        <PublishPreviewModal
          projectId={projectId}
          versionId={versionId}
          versionName={versionName}
          onPublished={() => {
            setOpen(false);
            showToast(`Publishing ${versionName} to Jira. It keeps going if you leave the page.`);
          }}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
