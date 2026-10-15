import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { TextField } from '@/components/TextField';
import { ApiError, describeError } from '@/lib/apiError';

import { isScopeStale } from './useScopeDecision';
import { isStale } from './types';
import type { ApprovalDecision, BacklogVersion } from './types';
import { useReject } from './useReject';

/** The API's limit on a rejection reason. */
const MAX_REASON = 2000;

interface RejectModalProps {
  projectId: string;
  version: BacklogVersion;
  /** What the version is called on the page, e.g. "Candidate v2". */
  name: string;
  /** The baseline that stays current, e.g. "v1"; null when there is none. */
  baseline: string | null;
  /** Loads the version again, after the server said the one on screen is out of date. */
  onReload: () => Promise<unknown>;
  onRejected: (decision: ApprovalDecision) => void;
  onClose: () => void;
}

/**
 * The approver's rejection of the version on screen, with a reason the audit trail keeps. Allowed
 * whatever scope decisions were recorded; the baseline stays as it is (ADR 0011).
 */
export function RejectModal({
  projectId,
  version,
  name,
  baseline,
  onReload,
  onRejected,
  onClose,
}: RejectModalProps) {
  const [reason, setReason] = useState('');
  const rejection = useReject(projectId);
  const error = rejection.error;
  const stale = isStale(error) || isScopeStale(error) ? error : null;
  const failure = error && !stale ? error : null;
  const trimmed = reason.trim();

  async function reload() {
    rejection.reset();
    await onReload();
    onClose();
  }

  return (
    <Modal
      title={`Reject ${name}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            disabled={trimmed === '' || stale !== null || rejection.isPending}
            onClick={() => {
              rejection.reject(version, trimmed, onRejected);
            }}
          >
            {rejection.isPending ? 'Rejecting…' : 'Reject'}
          </Button>
        </>
      }
    >
      <p>
        {baseline
          ? `Rejecting keeps ${baseline} as the current baseline, unchanged. ${name} stays in history as rejected.`
          : `Rejecting leaves the baseline unchanged. ${name} stays in history as rejected.`}
      </p>
      <TextField
        label="Reason"
        value={reason}
        onChange={setReason}
        rows={3}
        maxLength={MAX_REASON}
        help="Saved with the decision in the activity log."
        disabled={rejection.isPending}
      />
      {stale && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void reload()}>
              Reload
            </Button>
          }
        >
          {name} changed after you opened it, or was already decided. Nothing was rejected. Reload
          it and review it again.
        </Banner>
      )}
      {failure && (
        <Banner tone="bad" role="alert">
          {name} was not rejected. {describeError(failure)}
          {failure instanceof ApiError && failure.retryable && ' Try again in a moment.'}
        </Banner>
      )}
    </Modal>
  );
}
