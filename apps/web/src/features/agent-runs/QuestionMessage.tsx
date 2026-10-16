import { Card } from '@/components/Card';
import { useBacklogVersion } from '@/features/backlog';

import { AgentMessage } from './AgentMessage';
import { changeability } from './changeability';
import { QuestionCard } from './QuestionCard';
import type { ThreadContext } from './threadContext';
import type { Message } from './types';
import { useRun } from './useRun';

/** A question the agent asked, drawn from its run so it shows the question's state now. */
export function QuestionMessage({
  message,
  context,
}: {
  message: Message;
  context: ThreadContext;
}) {
  const runId = message.question?.run_id ?? message.run_id;
  const { data: run } = useRun(runId);
  const question = run?.questions.find((candidate) => candidate.id === message.question_id);
  // A question skipped here can be settled later on the backlog, as the decision it became.
  const skipped = question?.status === 'skipped';
  const { data: version } = useBacklogVersion(
    context.projectId,
    skipped ? (run?.candidate_version_id ?? null) : null,
  );
  const settled = skipped
    ? version?.decisions.find(
        (decision) => decision.question_id === question.id && decision.status === 'answered',
      )
    : undefined;
  if (!run || !question) {
    return (
      <AgentMessage>
        {/* Until its run loads, the question is shown as asked, without its controls. */}
        <Card>
          <p className="font-semibold">{message.text}</p>
        </Card>
      </AgentMessage>
    );
  }
  const { canChange, lockedNote } = settled
    ? { canChange: false, lockedNote: null }
    : changeability(run, question, context);
  return (
    <AgentMessage>
      <QuestionCard
        projectId={context.projectId}
        runId={run.id}
        question={question}
        canAnswer={context.canEdit && run.status === 'waiting_for_input'}
        canChange={canChange}
        lockedNote={lockedNote}
        answeredOnBacklog={
          settled ? { answer: settled.answer ?? '', by: settled.decided_by } : null
        }
        selected={question.id === context.answeringId}
        onAnswer={() => {
          context.onAnswer(run.id, question.id);
        }}
        onShowEvidence={() => {
          context.onShowEvidence({ type: 'question', runId: run.id, id: question.id });
        }}
      />
    </AgentMessage>
  );
}
