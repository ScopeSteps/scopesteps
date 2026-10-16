import { useId } from 'react';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Tag } from '@/components/Tag';
import type { TagTone } from '@/components/Tag';
import { useReviewerName } from '@/features/identity';
import { SourceCitationChip } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import type { Question } from './types';
import { useKeyedRunCommand } from './useKeyedRunCommand';

const STATUS: Record<Question['status'], { label: string; tone: TagTone }> = {
  open: { label: 'Needs an answer', tone: 'warn' },
  answered: { label: 'Answered', tone: 'ok' },
  skipped: { label: 'Skipped · still open', tone: 'bad' },
};

interface QuestionCardProps {
  projectId: string;
  runId: string;
  question: Question;
  /** The user may edit the project and the run still waits for answers. */
  canAnswer: boolean;
  /** An answer or skip can still be changed: its round is open or its draft is not decided. */
  canChange?: boolean;
  /** Why an answer can no longer be changed, when it cannot. */
  lockedNote?: string | null;
  /** A skipped question later answered on the backlog, as the decision it became. */
  answeredOnBacklog?: { answer: string; by: string | null } | null;
  /** The composer is answering this question. */
  selected: boolean;
  onAnswer: () => void;
  onShowEvidence: () => void;
}

export function QuestionCard({
  projectId,
  runId,
  question,
  canAnswer,
  canChange = false,
  lockedNote = null,
  answeredOnBacklog = null,
  selected,
  onAnswer,
  onShowEvidence,
}: QuestionCardProps) {
  const skip = useKeyedRunCommand(runId);
  const reviewerName = useReviewerName(projectId);
  const headingId = useId();
  const status = answeredOnBacklog
    ? { label: 'Answered on the backlog', tone: 'ok' as const }
    : STATUS[question.status];

  return (
    <Card tone={selected ? 'focus' : 'default'} role="article" aria-labelledby={headingId}>
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone={status.tone}>{status.label}</Tag>
        <span className="text-xs text-subtle">{question.subject}</span>
      </div>
      <h3 id={headingId} className="text-[15px] leading-[1.4] font-semibold">
        {question.text}
      </h3>
      <p className="text-xs text-subtle">
        {question.why_it_matters}{' '}
        {question.evidence.map((reference) => (
          <span key={reference.block_id} className="mr-1 inline-block">
            <SourceCitationChip
              projectId={projectId}
              sourceVersionId={reference.source_version_id}
              blockId={reference.block_id}
              onOpen={onShowEvidence}
            />
          </span>
        ))}
      </p>

      {question.status === 'open' && canAnswer && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            aria-pressed={selected}
            disabled={skip.isPending}
            onClick={onAnswer}
          >
            Answer
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={skip.isPending}
            onClick={() => {
              skip.send({ type: 'skip', questionId: question.id });
            }}
          >
            Skip
          </Button>
          {skip.isPending && (
            <span role="status" className="text-xs text-subtle">
              Saving…
            </span>
          )}
        </div>
      )}
      {skip.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          The question was not skipped. {describeError(skip.error)}
        </p>
      )}

      {question.status === 'answered' && (
        <>
          {/* Reviewer text is data: rendered as a text node. */}
          <blockquote className="m-0 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm whitespace-pre-wrap">
            {question.answer}
          </blockquote>
          <span className="text-xs text-subtle">
            Answered by {reviewerName(question.answered_by)}
          </span>
        </>
      )}
      {answeredOnBacklog && (
        <>
          <blockquote className="m-0 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm whitespace-pre-wrap">
            {answeredOnBacklog.answer}
          </blockquote>
          <span className="text-xs text-subtle">
            Skipped here, then answered on the backlog by {reviewerName(answeredOnBacklog.by)}.
          </span>
        </>
      )}
      {question.status === 'skipped' && !answeredOnBacklog && (
        <span className="text-xs text-subtle">
          Skipped by {reviewerName(question.answered_by)}. No answer was assumed, so it stays open
          and blocks the stories it affects.
        </span>
      )}
      {question.status !== 'open' && canChange && (
        <div>
          <Button size="sm" aria-pressed={selected} onClick={onAnswer}>
            {question.status === 'skipped' ? 'Answer now' : 'Change answer'}
          </Button>
        </div>
      )}
      {question.status !== 'open' && !canChange && lockedNote && (
        <span className="text-xs text-subtle">{lockedNote}</span>
      )}
    </Card>
  );
}
