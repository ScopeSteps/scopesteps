import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { useCurrentUser } from '@/features/identity';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { isStale, shortHash } from './types';
import type { ApprovalDecision, BacklogVersion, Check } from './types';
import { useApprove } from './useApprove';
import { useReview } from './useReview';

interface ApproveModalProps {
  projectId: string;
  version: BacklogVersion;
  /** The baseline number approval would create: 1 for v1. */
  baselineNumber: number;
  /** Loads the version again, after the server said what was reviewed is out of date. */
  onReload: () => Promise<unknown>;
  onApproved: (decision: ApprovalDecision) => void;
  onClose: () => void;
}

function CheckRow({ check }: { check: Check }) {
  const more = check.problem_count - check.problems.length;
  return (
    <li className="grid grid-cols-[22px_minmax(0,1fr)] gap-2.5">
      <span
        className={cx(
          'flex size-5 items-center justify-center rounded-full',
          check.passed ? 'bg-ok-soft text-ok-ink' : 'bg-bad-soft text-bad-ink',
        )}
      >
        <Icon name={check.passed ? 'check' : 'warn'} size={12} />
      </span>
      <div className="flex flex-col gap-0.5">
        <strong className="font-semibold">
          {check.title}
          <span className="sr-only">{check.passed ? ': passed' : ': not passed'}</span>
        </strong>
        {check.passed ? (
          <span className="text-xs text-subtle">Passed</span>
        ) : (
          <ul className="m-0 list-none p-0 text-xs text-subtle">
            {check.problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
            {more > 0 && <li>and {more} more</li>}
          </ul>
        )}
      </div>
    </li>
  );
}

/**
 * The approver's last look before a draft becomes a baseline: the server's checks on the
 * revision on screen, and exactly what approval binds to. Approve stays disabled until the
 * server says every check passed.
 */
export function ApproveModal({
  projectId,
  version,
  baselineNumber,
  onReload,
  onApproved,
  onClose,
}: ApproveModalProps) {
  const review = useReview(version.id, version.revision);
  const approval = useApprove(projectId);
  const { data: user } = useCurrentUser();
  const result = review.data;
  // A draft made before the current baseline cannot replace it (ADR 0008).
  const outdatedBase =
    result !== undefined && result.base_version_id !== result.baseline_version_id;
  const ready = result?.ready === true && !outdatedBase;
  const staleError = isStale(review.error)
    ? review.error
    : isStale(approval.error)
      ? approval.error
      : null;
  const label = `v${String(baselineNumber)}`;

  async function reviewAgain() {
    approval.reset();
    await onReload();
    await review.refetch();
  }

  let body;
  if (review.isPending) {
    body = (
      <p role="status" className="text-subtle">
        Running the server’s checks…
      </p>
    );
  } else if (!result) {
    body = !staleError && (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void review.refetch()}>
            Try again
          </Button>
        }
      >
        Could not run the approval checks. {describeError(review.error)}
      </Banner>
    );
  } else {
    body = (
      <>
        <ul aria-label="Approval checks" className="m-0 flex list-none flex-col gap-2.5 p-0">
          {result.checks.map((check) => (
            <CheckRow key={check.code} check={check} />
          ))}
        </ul>
        {outdatedBase && (
          <Banner tone="bad">
            This draft was made before the current baseline was approved, so it can’t replace it.
          </Banner>
        )}
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(110px,1fr))] gap-3">
          <div>
            <dt className="text-xs text-subtle">Revision</dt>
            <dd className="m-0 font-mono font-semibold tabular-nums">r{result.revision}</dd>
          </div>
          <div>
            <dt className="text-xs text-subtle">Content hash</dt>
            <dd className="m-0 font-mono font-semibold tabular-nums" title={result.content_hash}>
              {shortHash(result.content_hash)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-subtle">Stories</dt>
            <dd className="m-0 font-mono font-semibold tabular-nums">{result.story_count}</dd>
          </div>
          <div>
            <dt className="text-xs text-subtle">Approver</dt>
            <dd className="m-0 font-semibold">{user?.display_name ?? '…'}</dd>
          </div>
        </dl>
      </>
    );
  }

  const approvalError = approval.error && !isStale(approval.error) ? approval.error : null;

  return (
    <Modal
      title={`Approve baseline ${label}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>{ready ? 'Cancel' : 'Back to review'}</Button>
          <Button
            variant="primary"
            disabled={!ready || staleError !== null || approval.isPending}
            onClick={() => {
              if (result) {
                approval.approve(result, onApproved);
              }
            }}
          >
            {approval.isPending ? 'Approving…' : `Approve as ${label}`}
          </Button>
        </>
      }
    >
      <p>
        {baselineNumber === 1
          ? 'Approving freezes this exact revision as baseline v1. Later changes go through change requests.'
          : `Approving makes this exact revision baseline ${label}. v${String(baselineNumber - 1)} stays in history, unchanged.`}
      </p>
      {staleError && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void reviewAgain()}>
              Reload and review again
            </Button>
          }
        >
          This draft changed after you opened it, or another baseline was approved. Nothing was
          approved. {describeError(staleError)}
        </Banner>
      )}
      {body}
      {approvalError && (
        <Banner
          tone="bad"
          role="alert"
          action={
            approvalError instanceof ApiError && approvalError.code === 'APPROVAL_BLOCKED' ? (
              <Button size="sm" onClick={() => void reviewAgain()}>
                Review again
              </Button>
            ) : undefined
          }
        >
          The draft was not approved. {describeError(approvalError)}
          {approvalError instanceof ApiError &&
            approvalError.retryable &&
            ' Try again in a moment.'}
        </Banner>
      )}
    </Modal>
  );
}
