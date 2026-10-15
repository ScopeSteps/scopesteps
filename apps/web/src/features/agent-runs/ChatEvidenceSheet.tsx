import { SideSheet } from '@/components/SideSheet';
import { useReviewerName } from '@/features/identity';
import { SourcePassage } from '@/features/sources';

import { RunEvidenceSheet } from './RunEvidenceSheet';
import type { EvidenceRef, Message } from './types';
import { useRun } from './useRun';

interface ChatEvidenceSheetProps {
  projectId: string;
  evidence: EvidenceRef;
  /** The messages loaded in the thread, where a reply's citation is looked up. */
  messages: Message[];
  onClose: () => void;
}

const DISCLAIMER =
  'A citation shows where a detail came from. Whether it’s interpreted correctly is your call.';

/** The evidence behind a question, a finding or a reply's claim, in the side sheet. */
export function ChatEvidenceSheet({
  projectId,
  evidence,
  messages,
  onClose,
}: ChatEvidenceSheetProps) {
  if (evidence.type === 'reply') {
    return (
      <ReplyEvidence
        projectId={projectId}
        evidence={evidence}
        messages={messages}
        onClose={onClose}
      />
    );
  }
  return <RunEvidence projectId={projectId} evidence={evidence} onClose={onClose} />;
}

function RunEvidence({
  projectId,
  evidence,
  onClose,
}: {
  projectId: string;
  evidence: Exclude<EvidenceRef, { type: 'reply' }>;
  onClose: () => void;
}) {
  const { data: run, isPending } = useRun(evidence.runId);
  if (run) {
    return (
      <RunEvidenceSheet projectId={projectId} run={run} evidence={evidence} onClose={onClose} />
    );
  }
  return (
    <SideSheet title="Evidence" onClose={onClose}>
      {isPending ? (
        <p role="status" className="text-[13px] text-subtle">
          Loading the evidence…
        </p>
      ) : (
        <p role="alert" className="text-[13px] text-bad-ink">
          The run this evidence belongs to could not be loaded.
        </p>
      )}
    </SideSheet>
  );
}

function ReplyEvidence({
  projectId,
  evidence,
  messages,
  onClose,
}: {
  projectId: string;
  evidence: Extract<EvidenceRef, { type: 'reply' }>;
  messages: Message[];
  onClose: () => void;
}) {
  const reviewerName = useReviewerName(projectId);
  const message = messages.find((candidate) => candidate.id === evidence.messageId);
  const cited = message?.claims.flatMap((claim) =>
    claim.citations.map((citation) => ({ claim, citation })),
  )[evidence.citation];
  const question = messages.find(
    (candidate) => candidate.question?.id === cited?.citation.question_id,
  )?.question;

  return (
    <SideSheet title="Evidence" onClose={onClose}>
      {cited ? (
        <>
          <span className="text-xs text-subtle">What the agent said</span>
          <p className="font-medium">{cited.claim.text}</p>
          {cited.citation.evidence && (
            <SourcePassage
              projectId={projectId}
              sourceVersionId={cited.citation.evidence.source_version_id}
              blockId={cited.citation.evidence.block_id}
              quote={cited.citation.quote}
            />
          )}
          {cited.citation.question_id && (
            <figure className="m-0 flex flex-col gap-2">
              <figcaption className="text-xs text-subtle">
                {question
                  ? `Answer by ${reviewerName(question.answered_by)} · ${question.subject}`
                  : 'Recorded answer'}
              </figcaption>
              <blockquote className="m-0 rounded-[10px] border border-line bg-surface-2 px-3.5 py-3 text-[15px] leading-[1.55] whitespace-pre-wrap">
                {cited.citation.quote}
              </blockquote>
            </figure>
          )}
          <p className="text-xs text-subtle">{DISCLAIMER}</p>
        </>
      ) : (
        <p role="alert" className="text-[13px] text-bad-ink">
          This citation is not in the messages loaded in the thread.
        </p>
      )}
    </SideSheet>
  );
}
