import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { Icon } from '@/components/Icon';
import { CandidateDecisions } from '@/features/backlog';
import { changeRequestName, useChangeRequest } from '@/features/change-control';

import { AgentMessage } from './AgentMessage';
import { ChatEvent } from './ChatEvent';
import { FoundList } from './FoundList';
import { ProblemList } from './ProblemList';
import type { ThreadContext } from './threadContext';
import type { Message } from './types';
import { useRun } from './useRun';

/** What a finished run produced: its findings and the draft to open, read from the run. */
function ReadyMessage({ message, context }: { message: Message; context: ThreadContext }) {
  const { data: run } = useRun(message.run_id);
  return (
    <>
      <ChatEvent>{message.text}</ChatEvent>
      {run && (
        <AgentMessage>
          {run.mode === 'initial' && run.draft && run.draft.statements.length > 0 && (
            <FoundList
              projectId={context.projectId}
              run={run}
              statements={run.draft.statements}
              onShowCitation={(id, citation) => {
                context.onShowEvidence({ type: 'statement', runId: run.id, id, citation });
              }}
            />
          )}
          {run.mode === 'change' && run.candidate_version_id && (
            <CandidateDecisions
              projectId={context.projectId}
              versionId={run.candidate_version_id}
              onShowEvidence={(id) => {
                if (run.candidate_version_id) {
                  context.onShowEvidence({
                    type: 'decision',
                    versionId: run.candidate_version_id,
                    id,
                  });
                }
              }}
            />
          )}
          {run.problems.length > 0 && (
            <Banner tone="warn">
              Checks found problems the agent could not fix. Review the affected items with care:
              <ProblemList problems={run.problems} />
            </Banner>
          )}
          <p className="text-sm text-muted">
            Every detail links to a source or an answer. Nothing is final until a Product owner
            approves it.
          </p>
          {run.candidate_version_id && (
            <div>
              <ButtonLink size="sm" to={context.backlogHref(run.candidate_version_id)}>
                {run.mode === 'change' ? 'Review in backlog' : 'Open backlog'}
                <Icon name="right" size={14} />
              </ButtonLink>
            </div>
          )}
        </AgentMessage>
      )}
    </>
  );
}

/** Something that happened to a run, as the server worded it. */
export function EventMessage({ message, context }: { message: Message; context: ThreadContext }) {
  switch (message.event) {
    case 'run.ready_for_review':
    case 'change.ready_for_review':
      return <ReadyMessage message={message} context={context} />;
    case 'run.failed':
    case 'reply.failed':
      return (
        <>
          <ChatEvent>{message.event === 'run.failed' ? 'Run failed' : 'Reply failed'}</ChatEvent>
          <AgentMessage>
            <Banner tone="bad">
              Nothing was approved or changed. {message.text || 'No reason was recorded.'}
            </Banner>
            <NewRunOffer message={message} context={context} />
          </AgentMessage>
        </>
      );
    case 'run.cancelled':
      return (
        <>
          <ChatEvent>{message.text}</ChatEvent>
          <NewRunOffer message={message} context={context} />
        </>
      );
    case 'change.approved':
    case 'change.rejected':
      return <ChangeOutcome message={message} context={context} />;
    case 'change.no_change_needed':
      return (
        <>
          <ChatEvent>{message.text}</ChatEvent>
          <AgentMessage>
            <p className="text-sm text-muted">
              No change needed. No candidate was saved, and the approved baseline stays as it is.
            </p>
          </AgentMessage>
        </>
      );
    default:
      return <ChatEvent>{message.text}</ChatEvent>;
  }
}

/**
 * An approver's decision on a change candidate, as the server worded it ("CR-1 was approved as
 * baseline v2."). It is the one place the thread reports the outcome, at the time it happened;
 * it links to the version it produced and to the request on the Change requests page.
 */
function ChangeOutcome({ message, context }: { message: Message; context: ThreadContext }) {
  const { data: request } = useChangeRequest(message.change_request_id ?? null);
  const approved = message.event === 'change.approved';
  const name = request ? changeRequestName(request.number) : 'the change request';
  return (
    <>
      <ChatEvent>{approved ? 'Change approved' : 'Change rejected'}</ChatEvent>
      <AgentMessage>
        <p className="text-sm font-semibold">{message.text}</p>
        <p className="text-sm text-muted">
          {approved
            ? 'The earlier baseline stays in history, unchanged.'
            : 'Nothing in the approved scope changed.'}
        </p>
        <div className="flex flex-wrap gap-2">
          {approved && request?.candidate_version_id && (
            <ButtonLink size="sm" to={context.backlogHref(request.candidate_version_id)}>
              {message.baseline_version === null
                ? 'Open the new baseline'
                : `Open baseline v${String(message.baseline_version)}`}
              <Icon name="right" size={14} />
            </ButtonLink>
          )}
          <ButtonLink size="sm" to={context.changesHref} aria-label={`Change requests: ${name}`}>
            Change requests
          </ButtonLink>
        </div>
      </AgentMessage>
    </>
  );
}

function NewRunOffer({ message, context }: { message: Message; context: ThreadContext }) {
  if (!context.canEdit || message.id !== context.latestId || message.event?.startsWith('reply')) {
    return null;
  }
  return (
    <div>
      <Button size="sm" onClick={context.onStartNewRun}>
        Start a new run
      </Button>
    </div>
  );
}
