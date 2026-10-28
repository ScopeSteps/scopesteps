import { CitationChip } from '@/components/CitationChip';
import { Tag } from '@/components/Tag';
import { SourceCitationChip } from '@/features/sources';

import { AgentMessage } from './AgentMessage';
import { DecisionCard } from './DecisionCard';
import { EventMessage } from './EventMessage';
import { QuestionMessage } from './QuestionMessage';
import { SuggestionCard } from './SuggestionCard';
import type { ThreadContext } from './threadContext';
import type { Message } from './types';
import { useAuthorName } from './useAuthorName';
import { UserBubble } from './UserBubble';

function Claims({ message, context }: { message: Message; context: ThreadContext }) {
  // A citation is opened by its position among all of the message's citations.
  const offsets = message.claims.map((_, claimIndex) =>
    message.claims.slice(0, claimIndex).reduce((total, claim) => total + claim.citations.length, 0),
  );
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {message.claims.map((claim, claimIndex) => (
        // Claims never change once stored, so their position is a stable key.
        <li key={claimIndex}>
          {claim.text}{' '}
          {claim.basis === 'agent' && (
            <Tag tone="warn" className="align-middle">
              Agent’s own words · no evidence
            </Tag>
          )}
          {claim.citations.map((citation, citationIndex) => {
            const index = (offsets[claimIndex] ?? 0) + citationIndex;
            const open = () => {
              context.onShowEvidence({ type: 'reply', messageId: message.id, citation: index });
            };
            return (
              <span key={index} className="ml-1 inline-block">
                {citation.evidence ? (
                  <SourceCitationChip
                    projectId={context.projectId}
                    sourceVersionId={citation.evidence.source_version_id}
                    blockId={citation.evidence.block_id}
                    about={claim.text}
                    onOpen={open}
                  />
                ) : (
                  <CitationChip onClick={open} aria-label={`Answer, evidence for: ${claim.text}`}>
                    Answer
                  </CitationChip>
                )}
              </span>
            );
          })}
        </li>
      ))}
    </ul>
  );
}

/** One stored message, drawn by its kind. */
export function ThreadMessage({ message, context }: { message: Message; context: ThreadContext }) {
  const authorName = useAuthorName(context.projectId);
  switch (message.kind) {
    case 'message':
    case 'discuss':
    case 'change_request':
      return (
        <UserBubble
          author={authorName(message.author)}
          at={message.created_at}
          kind={message.kind}
          text={message.text}
        />
      );
    case 'reply':
    case 'analysis':
      return (
        <AgentMessage>
          {message.kind === 'analysis' && (
            <span className="text-xs text-subtle">Change analysis</span>
          )}
          <Claims message={message} context={context} />
          {message.suggestion && (
            <SuggestionCard
              messageId={message.id}
              suggestion={message.suggestion}
              context={context}
            />
          )}
        </AgentMessage>
      );
    case 'question':
      return <QuestionMessage message={message} context={context} />;
    case 'answer':
    case 'skip':
    case 'answer_changed':
      return <DecisionCard message={message} context={context} />;
    case 'event':
      return <EventMessage message={message} context={context} />;
  }
}
