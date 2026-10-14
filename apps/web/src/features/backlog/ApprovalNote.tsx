import type { components } from '@scopesteps/api-client';

import { useMemberName } from '@/features/identity';

import { formatWhen, shortHash } from './types';
import type { BacklogVersion } from './types';

type Approval = components['schemas']['VersionDecisionResponse'];

interface ApprovalNoteProps {
  projectId: string;
  version: BacklogVersion;
  /** How the version was approved, from the history; null until the history has loaded. */
  approval: Approval | null;
  /** The current baseline's number when it is a later version than this one. */
  baseline: number | null;
  note: string;
}

/** Who approved an approved version and when, its content hash, and that it is read-only. */
export function ApprovalNote({ projectId, version, approval, baseline, note }: ApprovalNoteProps) {
  const memberName = useMemberName(projectId);
  const approver = approval ? memberName(approval.decided_by) : null;

  return (
    <p className="-mt-2 text-xs text-subtle">
      {approval ? (
        <>
          Approved{approver && ` by ${approver}`} at{' '}
          <time dateTime={approval.decided_at}>{formatWhen(approval.decided_at)}</time>
        </>
      ) : (
        'Approved'
      )}
      {' · '}
      <span className="font-mono tabular-nums" title={version.content_hash}>
        {shortHash(version.content_hash)}
      </span>
      {' · read-only. '}
      {baseline !== null && `The current baseline is v${String(baseline)}. `}
      {note}
    </p>
  );
}
