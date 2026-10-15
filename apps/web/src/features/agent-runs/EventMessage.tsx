import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { Icon } from '@/components/Icon';

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
                Open backlog
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
    default:
      return <ChatEvent>{message.text}</ChatEvent>;
  }
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
