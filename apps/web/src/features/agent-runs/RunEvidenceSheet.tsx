import { Button } from '@/components/Button';
import { SideSheet } from '@/components/SideSheet';
import { Tag } from '@/components/Tag';
import { useReviewerName } from '@/features/identity';
import { SourcePassage, useBlockSource } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import type { EvidenceRef, Run } from './types';

interface RunEvidenceSheetProps {
  projectId: string;
  run: Run;
  evidence: EvidenceRef;
  onClose: () => void;
}

const DISCLAIMER =
  'A citation shows where a detail came from. Whether it’s interpreted correctly is your call.';

function NotFound() {
  return (
    <p role="alert" className="text-[13px] text-bad-ink">
      This link does not match anything in this run.
    </p>
  );
}

/** A source block the draft cites by id, looked up among the versions the run read. */
function CitedBlock({
  projectId,
  run,
  blockId,
  quote,
}: {
  projectId: string;
  run: Run;
  blockId: string;
  quote: string;
}) {
  const located = useBlockSource(projectId, run.source_version_ids, blockId);
  switch (located.status) {
    case 'pending':
      return (
        <p role="status" className="text-[13px] text-subtle">
          Loading the cited passage…
        </p>
      );
    case 'error':
      return (
        <div role="alert" className="flex flex-col items-start gap-1.5 text-[13px] text-bad-ink">
          <p>Could not load the cited passage. {describeError(located.error)}</p>
          <Button size="sm" onClick={located.retry}>
            Try again
          </Button>
        </div>
      );
    case 'missing':
      return (
        <p role="alert" className="text-[13px] text-bad-ink">
          This citation points at a paragraph that is not in the sources this run read.
        </p>
      );
    case 'found':
      return (
        <SourcePassage
          projectId={projectId}
          sourceVersionId={located.sourceVersionId}
          blockId={blockId}
          quote={quote}
        />
      );
  }
}

/** The evidence behind a question or one citation in the agent's findings. */
export function RunEvidenceSheet({ projectId, run, evidence, onClose }: RunEvidenceSheetProps) {
  const reviewerName = useReviewerName();

  if (evidence.type === 'question') {
    const question = run.questions.find((candidate) => candidate.id === evidence.id);
    return (
      <SideSheet title="Evidence" onClose={onClose}>
        {question ? (
          <>
            <span className="text-xs text-subtle">Question · {question.subject}</span>
            <p className="font-medium">{question.text}</p>
            <ul className="m-0 flex list-none flex-col gap-4 p-0">
              {question.evidence.map((reference) => (
                <li key={reference.block_id} className="flex flex-col gap-1.5">
                  {reference.relationship === 'conflicting' && (
                    <Tag tone="bad" className="self-start">
                      Conflicting passage
                    </Tag>
                  )}
                  <SourcePassage
                    projectId={projectId}
                    sourceVersionId={reference.source_version_id}
                    blockId={reference.block_id}
                    quote={reference.quote}
                  />
                </li>
              ))}
            </ul>
            <p className="text-xs text-subtle">{DISCLAIMER}</p>
          </>
        ) : (
          <NotFound />
        )}
      </SideSheet>
    );
  }

  const statement = run.draft?.statements.find((candidate) => candidate.id === evidence.id);
  const citation = statement?.citations[evidence.citation];
  const ref = run.block_refs.find((candidate) => candidate.label === citation?.block_id);
  const answered = run.questions.find((candidate) => candidate.id === ref?.question_id);

  return (
    <SideSheet title="Evidence" onClose={onClose}>
      {statement && citation && ref ? (
        <>
          <span className="text-xs text-subtle">What the agent found</span>
          <p className="font-medium">{statement.summary}</p>
          {ref.source_block_id && (
            <CitedBlock
              projectId={projectId}
              run={run}
              blockId={ref.source_block_id}
              quote={citation.quote}
            />
          )}
          {answered && (
            <figure className="m-0 flex flex-col gap-2">
              <figcaption className="text-xs text-subtle">
                Answer by {reviewerName(answered.answered_by)}
                {answered.answered_at && (
                  <>
                    {' · '}
                    <time dateTime={answered.answered_at}>
                      {new Date(answered.answered_at).toLocaleString()}
                    </time>
                  </>
                )}
              </figcaption>
              <blockquote className="m-0 rounded-[10px] border border-line bg-surface-2 px-3.5 py-3 text-[15px] leading-[1.55] whitespace-pre-wrap">
                {answered.answer}
              </blockquote>
              <p className="text-xs text-subtle">Question: {answered.text}</p>
            </figure>
          )}
          <p className="text-xs text-subtle">{DISCLAIMER}</p>
        </>
      ) : (
        <NotFound />
      )}
    </SideSheet>
  );
}
