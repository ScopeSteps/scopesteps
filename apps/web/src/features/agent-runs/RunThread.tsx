import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { Icon } from '@/components/Icon';
import { plural, useSources } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import { AgentMessage } from './AgentMessage';
import { ChatEvent } from './ChatEvent';
import { FoundList } from './FoundList';
import { ProblemList } from './ProblemList';
import { QuestionCard } from './QuestionCard';
import { canAdvance } from './types';
import type { EvidenceRef, Question, Run } from './types';
import { useStopRun } from './useStopRun';

export interface RunDriverState {
  isAdvancing: boolean;
  requestError: Error | null;
  retry: () => void;
}

interface RunThreadProps {
  projectId: string;
  run: Run;
  canEdit: boolean;
  driver: RunDriverState;
  answeringId: string | null;
  onAnswer: (questionId: string) => void;
  onShowEvidence: (ref: EvidenceRef) => void;
  onStartNewRun: () => void;
  backlogHref: (versionId: string) => string;
}

const WORKING_DOT_DELAYS = ['', '[animation-delay:150ms]', '[animation-delay:300ms]'];

function byRound(questions: Question[]): Question[][] {
  const rounds = new Map<number, Question[]>();
  for (const question of questions) {
    rounds.set(question.round, [...(rounds.get(question.round) ?? []), question]);
  }
  return [...rounds.entries()].sort(([a], [b]) => a - b).map(([, round]) => round);
}

function roundIntro(round: Question[], isFirst: boolean): string {
  if (isFirst) {
    return `I need ${round.length === 1 ? 'one answer' : `${String(round.length)} answers`} before I draft the backlog. You can skip a question; it then stays open and blocks the stories it affects.`;
  }
  return `Your answers raised ${round.length === 1 ? 'one more question' : `${String(round.length)} more questions`}.`;
}

/** The run told as a conversation: everything in it comes from the run the API returned. */
export function RunThread({
  projectId,
  run,
  canEdit,
  driver,
  answeringId,
  onAnswer,
  onShowEvidence,
  onStartNewRun,
  backlogHref,
}: RunThreadProps) {
  const { data: versions } = useSources(projectId);
  const cancel = useStopRun(run.id);
  const rounds = byRound(run.questions);
  const stalled = run.error !== null || driver.requestError !== null;
  const working = canAdvance(run) && !stalled;
  const questionsHandled =
    run.questions.length > 0 && run.questions.every((question) => question.status !== 'open');
  const items = run.draft?.items ?? [];
  const epics = items.filter((item) => item.kind === 'epic').length;
  const stories = items.filter((item) => item.kind === 'story').length;

  const sourceNames = run.source_version_ids.map((id) => {
    const version = versions?.find((candidate) => candidate.id === id);
    return version
      ? `${version.filename} v${String(version.version)}`
      : 'an earlier source version';
  });

  const startNewRun = canEdit && (
    <div>
      <Button size="sm" onClick={onStartNewRun}>
        Start a new run
      </Button>
    </div>
  );

  return (
    <>
      <h2 className="sr-only">Conversation with the agent</h2>
      <ChatEvent>
        {versions ? `Run started on ${sourceNames.join(' and ')}` : 'Run started'}
      </ChatEvent>
      {run.fallback_reason && (
        <Banner>
          The agent is using its backup provider ({run.provider}). {run.fallback_reason}
        </Banner>
      )}

      {rounds.map((round, index) => {
        const isLast = index === rounds.length - 1;
        return (
          <AgentMessage key={round[0]?.round ?? index}>
            <p>{roundIntro(round, index === 0)}</p>
            {round.map((question) => (
              <QuestionCard
                key={question.id}
                projectId={projectId}
                runId={run.id}
                question={question}
                canAnswer={canEdit && run.status === 'waiting_for_input'}
                selected={question.id === answeringId}
                onAnswer={() => {
                  onAnswer(question.id);
                }}
                onShowEvidence={() => {
                  onShowEvidence({ type: 'question', id: question.id });
                }}
              />
            ))}
            {isLast && run.status === 'waiting_for_input' && canEdit && (
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={cancel.stop}>
                  Stop the run
                </Button>
                {cancel.error && (
                  <span role="alert" className="text-[13px] text-bad-ink">
                    The run was not stopped. {describeError(cancel.error)}
                  </span>
                )}
              </div>
            )}
          </AgentMessage>
        );
      })}

      {questionsHandled && run.status !== 'waiting_for_input' && (
        <ChatEvent>All questions handled. Drafting the backlog.</ChatEvent>
      )}

      {working && (
        <AgentMessage>
          <div role="status" className="flex items-center gap-2.5 text-sm text-muted">
            <span aria-hidden="true" className="flex gap-1">
              {WORKING_DOT_DELAYS.map((delay) => (
                <span
                  key={delay}
                  className={`size-1.5 animate-working rounded-full bg-accent ${delay}`}
                />
              ))}
            </span>
            {run.stage === 'draft'
              ? 'Drafting the backlog from your sources and answers…'
              : 'Reading the sources…'}
          </div>
          <p className="text-xs text-subtle">
            {canEdit
              ? 'One step can take up to half a minute. You can leave this page; the run is saved and resumes when you come back.'
              : 'An editor’s session moves the run on. This page shows their progress.'}
          </p>
        </AgentMessage>
      )}

      {canAdvance(run) && run.error && (
        <Banner
          tone="bad"
          role="alert"
          action={
            canEdit && (
              <Button size="sm" onClick={driver.retry}>
                Try the step again
              </Button>
            )
          }
        >
          The last step failed and nothing was lost. {run.error.message}
        </Banner>
      )}
      {driver.requestError && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={driver.retry}>
              Try the step again
            </Button>
          }
        >
          The run could not be advanced. {describeError(driver.requestError)}
        </Banner>
      )}

      {run.status === 'ready_for_review' && (
        <>
          {run.draft && run.draft.statements.length > 0 && (
            <AgentMessage>
              <FoundList
                statements={run.draft.statements}
                onShowCitation={(id, citation) => {
                  onShowEvidence({ type: 'statement', id, citation });
                }}
              />
            </AgentMessage>
          )}
          <ChatEvent>Draft ready</ChatEvent>
          <AgentMessage>
            <p>
              I drafted{' '}
              <strong>
                {plural(epics, 'epic')} and {plural(stories, 'story', 'stories')}
              </strong>
              . Every detail links to a source or to one of your answers. Nothing is final until a
              Product owner approves it.
            </p>
            {run.problems.length > 0 && (
              <Banner tone="warn">
                Checks found problems I could not fix. Review the affected items with care:
                <ProblemList problems={run.problems} />
              </Banner>
            )}
            {run.candidate_version_id && (
              <div>
                <ButtonLink size="sm" to={backlogHref(run.candidate_version_id)}>
                  Open backlog
                  <Icon name="right" size={14} />
                </ButtonLink>
              </div>
            )}
          </AgentMessage>
        </>
      )}

      {run.status === 'failed' && (
        <>
          <ChatEvent>Run failed</ChatEvent>
          <AgentMessage>
            <Banner tone="bad" role="alert">
              The run stopped and no backlog was approved or changed.{' '}
              {run.error?.message ?? 'No reason was recorded.'}
              <ProblemList problems={run.problems} />
            </Banner>
            {startNewRun}
          </AgentMessage>
        </>
      )}

      {run.status === 'cancelled' && (
        <>
          <ChatEvent>Run stopped</ChatEvent>
          <AgentMessage>
            <p>This run was stopped. Nothing was approved or changed.</p>
            {startNewRun}
          </AgentMessage>
        </>
      )}
    </>
  );
}
