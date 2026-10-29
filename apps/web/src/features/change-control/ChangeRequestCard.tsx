import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';

import { ButtonLink } from '@/components/ButtonLink';
import { Card } from '@/components/Card';
import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { Tag } from '@/components/Tag';

import { ImpactPanel } from './ImpactPanel';
import { changeRequestName, STATUSES } from './types';
import type { ChangeRequest } from './types';
import { formatWhen } from '@/lib/formatWhen';

export interface ChangeRequestLinks {
  /** Where the backlog page shows a version. */
  versionHref: (versionId: string) => string;
  /** Where the chat shows the run that analysed the request. */
  chatHref: (runId: string) => string;
}

interface ChangeRequestCardProps extends ChangeRequestLinks {
  request: ChangeRequest;
  /** The scope decisions the candidate reverses, drawn by the page that knows the backlog. */
  conflict?: ReactNode;
  /** The request a link asked for: brought into view and marked. */
  focused?: boolean;
}

function baseName(request: ChangeRequest): string {
  return request.base_version_number === null
    ? 'the baseline'
    : `v${String(request.base_version_number)}`;
}

const SUMMARY: { key: 'added' | 'changed' | 'removed'; kind: DiffKind; verb: string }[] = [
  { key: 'added', kind: 'added', verb: 'added' },
  { key: 'changed', kind: 'changed', verb: 'changed' },
  { key: 'removed', kind: 'removed', verb: 'removed' },
];

function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${String(count)} ${count === 1 ? noun : many}`;
}

/** What became of the request, as its status says. */
function outcome(request: ChangeRequest): string {
  const base = baseName(request);
  switch (request.status) {
    case 'analyzing':
      return `The agent is comparing it with ${base}.`;
    case 'in_review':
      return `A candidate is in review; ${base} stays unchanged unless it’s approved.`;
    case 'no_change_needed':
      return `No change needed: ${base} already covers this request.`;
    case 'approved':
      return request.approved_version_number === null
        ? `Approved. Its candidate replaced ${base} as the baseline.`
        : `Approved as v${String(request.approved_version_number)}. It replaced ${base} as the baseline.`;
    case 'rejected':
      return `Rejected; ${base} is unchanged.`;
    case 'failed':
      return `The analysis did not finish${request.failure ? ` (${request.failure})` : ''}. Nothing changed; send the request again.`;
  }
}

/** What the link to the request's candidate says: an approved one is named by its version. */
function versionAction(request: ChangeRequest): string {
  if (request.status === 'in_review') {
    return 'Review in backlog';
  }
  return request.status === 'approved' && request.approved_version_number !== null
    ? `Open v${String(request.approved_version_number)}`
    : 'Open candidate';
}

/** One change request: what was asked, against which version, and what came of it. */
export function ChangeRequestCard({
  request,
  conflict,
  focused = false,
  versionHref,
  chatHref,
}: ChangeRequestCardProps) {
  const headingId = useId();
  const card = useRef<HTMLDivElement>(null);
  const status = STATUSES[request.status];
  const name = changeRequestName(request.number);
  useEffect(() => {
    // jsdom has no layout, so it has no scrollIntoView either.
    if (focused && typeof card.current?.scrollIntoView === 'function') {
      card.current.scrollIntoView({ block: 'start' });
    }
  }, [focused]);
  return (
    <Card
      ref={card}
      role="article"
      aria-labelledby={headingId}
      aria-current={focused ? 'true' : undefined}
      tone={focused ? 'focus' : 'default'}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="font-mono text-[13px] font-semibold tabular-nums">
          {name}
        </h3>
        <Tag tone={status.tone}>{status.label}</Tag>
        <span className="ml-auto text-xs text-subtle">Compared with {baseName(request)}</span>
      </div>
      <p className="text-[15px] whitespace-pre-wrap">{request.text}</p>
      <span className="text-xs text-subtle">
        Requested by {request.requested_by.display_name} ·{' '}
        <time dateTime={request.requested_at}>{formatWhen(request.requested_at)}</time>
      </span>
      {request.analysis && (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-subtle">The agent’s analysis</span>
          <p className="text-muted">{request.analysis}</p>
        </div>
      )}
      {conflict}
      {request.impact && <ImpactPanel impact={request.impact} name={name} />}
      {request.summary && (
        <div className="flex flex-col gap-1.5">
          <ul aria-label={`Summary of changes in ${name}`} className="flex flex-wrap gap-3">
            {SUMMARY.map(({ key, kind, verb }) => (
              <li key={key} className="flex items-center gap-1.5 text-[13px]">
                <DiffTag kind={kind} />
                {plural(request.summary?.[key] ?? 0, 'item')} {verb}
              </li>
            ))}
          </ul>
          <span className="text-xs text-subtle">Everything else keeps its ID and content.</span>
        </div>
      )}
      <p role={request.status === 'analyzing' ? 'status' : undefined} className="text-[13px]">
        {outcome(request)}
      </p>
      <div className="flex flex-wrap gap-2">
        {request.candidate_version_id && (
          <ButtonLink
            size="sm"
            variant={request.status === 'in_review' ? 'primary' : 'default'}
            to={versionHref(request.candidate_version_id)}
            aria-label={`${versionAction(request)}: ${name}`}
          >
            {versionAction(request)}
          </ButtonLink>
        )}
        <ButtonLink size="sm" to={chatHref(request.run_id)} aria-label={`Open chat: ${name}`}>
          Open chat
        </ButtonLink>
      </div>
    </Card>
  );
}
