import { tokenMessage } from './tokenState';
import { useJiraConnection } from './useJiraConnection';

interface AlsoPublishToJiraProps {
  projectId: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}

/**
 * The approve window's "Also publish to Jira", unchecked by default. Shown only while Jira is
 * connected and you may publish; with automatic publishing on, it says so instead.
 */
export function AlsoPublishToJira({
  projectId,
  checked,
  disabled = false,
  onChange,
}: AlsoPublishToJiraProps) {
  const { data: status } = useJiraConnection(projectId);
  const connection = status?.connection;
  if (!connection || !status.can_publish || tokenMessage(connection)?.stopped === true) {
    return null;
  }
  if (connection.auto_publish) {
    return (
      <p className="text-xs text-subtle">
        This project publishes approved versions to Jira project {connection.jira_project_key}{' '}
        automatically.
      </p>
    );
  }
  return (
    <label className="flex cursor-pointer items-start gap-2 text-[13px]">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        className="mt-0.5 size-4 accent-[var(--accent)]"
      />
      <span className="flex flex-col">
        <span>Also publish to Jira</span>
        <span className="text-xs text-subtle">
          Sends this version to Jira project {connection.jira_project_key} right after approval.
        </span>
      </span>
    </label>
  );
}
