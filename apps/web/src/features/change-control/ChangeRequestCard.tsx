import { useId } from 'react';
import type { ReactNode } from 'react';

import { ButtonLink } from '@/components/ButtonLink';
import { Card } from '@/components/Card';
import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { Tag } from '@/components/Tag';

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
      return `Approved. Its candidate replaced ${base} as the baseline.`;
    case 'rejected':
      return `Rejected; ${base} is unchanged.`;
    case 'failed':
      return `The analysis did not finish${request.failure ? ` (${request.failure})` : ''}. Nothing changed; send the request again.`;
  }
}

/** One change request: what was asked, against which version, and what came of it. */
export function ChangeRequestCard({
  request,
  conflict,
  versionHref,
  chatHref,
}: ChangeRequestCardProps) {
  const headingId = useId();
  const status = STATUSES[request.status];
  const name = changeRequestName(request.number);
  return (
    <Card role="article" aria-labelledby={headingId}>
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
            aria-label={`${request.status === 'in_review' ? 'Review in backlog' : 'Open candidate'}: ${name}`}
          >
            {request.status === 'in_review' ? 'Review in backlog' : 'Open candidate'}
          </ButtonLink>
        )}
        <ButtonLink size="sm" to={chatHref(request.run_id)} aria-label={`Open chat: ${name}`}>
          Open chat
        </ButtonLink>
      </div>
    </Card>
  );
}
