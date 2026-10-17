import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { useBacklogVersion } from '@/features/backlog';
import { useCanApprove, useCanEdit, useCurrentUser } from '@/features/identity';
import { useSources } from '@/features/sources';
import { useProject } from '@/features/projects';
import { describeError } from '@/lib/apiError';

import { ActiveRunProgress } from './ActiveRunProgress';
import { ChatEvidenceSheet } from './ChatEvidenceSheet';
import { Composer } from './Composer';
import type { ChangeRequestOption } from './Composer';
import { NewChatIntro } from './NewChatIntro';
import { OutgoingBubble } from './OutgoingBubble';
import { changeability } from './changeability';
import { ThreadMessage } from './ThreadMessage';
import type { ThreadContext } from './threadContext';
import { canAdvance, conversationQueryKey, evidenceParam, parseEvidenceParam } from './types';
import type { EvidenceRef } from './types';
import { useConversation } from './useConversation';
import { useOutbox } from './useOutbox';
import { useRun } from './useRun';
import { useRunDriver } from './useRunDriver';
import { useStickToBottom } from './useStickToBottom';

interface ChatViewProps {
  projectId: string;
  /** The run last started from this page, kept in the URL for the run details in the top bar. */
  runId: string | null;
  onRunSelected: (runId: string | null) => void;
  /** Where the backlog page shows a version, so the thread can link to the draft. */
  backlogHref: (versionId: string) => string;
  /** The project's Change requests page, which change outcomes link to. */
  changesHref: string;
}

/** The thread and the composer under it, filling the page so the composer stays in view. */
function ChatLayout({
  thread,
  composer,
  scrollerRef,
  contentRef,
}: {
  thread: ReactNode;
  composer: ReactNode;
  scrollerRef: RefObject<HTMLDivElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-auto">
        <div
          ref={contentRef}
          className="mx-auto flex max-w-[760px] flex-col gap-[22px] px-5 pt-7 pb-3 max-wide:px-4"
        >
          {thread}
        </div>
      </div>
      {composer}
    </div>
  );
}

/** Why a change request cannot be sent now, from the project's scope state (ADR 0011). */
function changeRequestOption(
  state: string | undefined,
  base: { versionId: string; contentHash: string } | null,
): ChangeRequestOption {
  switch (state) {
    case 'baseline':
      return base
        ? { available: true, base }
        : { available: false, reason: 'Loading the approved baseline…' };
    case 'candidate_in_review':
      return {
        available: false,
        reason: 'A change is in review. Approve or reject it before requesting another.',
      };
    case 'draft_in_progress':
      return {
        available: false,
        reason: 'A draft is in review. Approve or reject it before requesting a change.',
      };
    case 'no_baseline':
      return {
        available: false,
        reason: 'Change requests need an approved baseline to change.',
      };
    default:
      return { available: false, reason: 'Loading the project…' };
  }
}

/**
 * The project's conversation with the agent, as the server stores it: messages, replies with
 * citations, questions, decisions and events, with the composer under it.
 */
export function ChatView({ projectId, onRunSelected, backlogHref, changesHref }: ChatViewProps) {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const editRole = useCanEdit(projectId);
  const approveRole = useCanApprove(projectId);
  const { data: sources } = useSources(projectId);
  const canEdit = user ? editRole : null;
  const conversation = useConversation(projectId, { watch: canEdit === false });
  const { data: project } = useProject(projectId);
  const scope = project?.status;
  const baselineId = scope?.state === 'baseline' ? scope.baseline_version_id : null;
  const { data: baseline } = useBacklogVersion(projectId, baselineId);
  const outbox = useOutbox(projectId);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const threadContent = useRef<HTMLDivElement>(null);
  const { scrollToLatest } = useStickToBottom(scroller, threadContent);
  const [answeringRef, setAnsweringRef] = useState<{ runId: string; questionId: string } | null>(
    null,
  );
  const [showSetup, setShowSetup] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const evidence = parseEvidenceParam(searchParams.get('evidence'));

  const { data: activeRun } = useRun(conversation.activeRun?.id ?? null, {
    watch: canEdit === false,
  });
  const driver = useRunDriver(activeRun, canEdit === true);
  const { data: answeringRun } = useRun(answeringRef?.runId ?? null);

  // A question answered or locked meanwhile (another tab, a refresh) is no longer one to answer.
  const answeringQuestion = answeringRun?.questions.find(
    (question) => question.id === answeringRef?.questionId,
  );
  const answering =
    answeringRun &&
    answeringQuestion &&
    ((answeringQuestion.status === 'open' && answeringRun.status === 'waiting_for_input') ||
      changeability(answeringRun, answeringQuestion, { canEdit: canEdit === true, scope })
        .canChange)
      ? { run: answeringRun, question: answeringQuestion }
      : null;

  function showEvidence(ref: EvidenceRef | null) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (ref) {
        next.set('evidence', evidenceParam(ref));
      } else {
        next.delete('evidence');
      }
      return next;
    });
  }

  const messages = conversation.messages;
  const context: ThreadContext = {
    projectId,
    canEdit: canEdit === true,
    scope,
    answeringId: answering?.question.id ?? null,
    onAnswer: (runId, questionId) => {
      setAnsweringRef({ runId, questionId });
    },
    onShowEvidence: showEvidence,
    backlogHref,
    changesHref,
    onStartNewRun: () => {
      setShowSetup(true);
    },
    canApprove: approveRole,
    baseline: baseline ? { versionId: baseline.id, contentHash: baseline.content_hash } : null,
    sourceVersionIds: sources?.map((version) => version.id) ?? [],
    onRunStarted: (runId) => {
      onRunSelected(runId);
      void queryClient.invalidateQueries({ queryKey: conversationQueryKey(projectId) });
    },
    latestId: messages.at(-1)?.id ?? null,
  };

  const working = activeRun && canAdvance(activeRun) ? activeRun : null;
  const isEmpty =
    messages.length === 0 && conversation.activeRun === null && outbox.outbox.length === 0;
  const intro = (
    <NewChatIntro
      projectId={projectId}
      canEdit={canEdit === true}
      reveal={showSetup && !isEmpty}
      onRunSelected={(runId) => {
        setShowSetup(false);
        onRunSelected(runId);
        void queryClient.invalidateQueries({ queryKey: conversationQueryKey(projectId) });
      }}
      backlogHref={backlogHref}
    />
  );

  let thread: ReactNode;
  if (conversation.isPending) {
    thread = (
      <p role="status" className="text-subtle">
        Loading the conversation…
      </p>
    );
  } else if (conversation.isError && messages.length === 0) {
    thread = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void conversation.refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the conversation. {describeError(conversation.error)}
      </Banner>
    );
  } else {
    thread = (
      <>
        <h2 className="sr-only">Conversation with the agent</h2>
        {conversation.hasNextPage && (
          <div className="flex justify-center">
            <Button
              size="sm"
              variant="ghost"
              disabled={conversation.isFetchingNextPage}
              onClick={() => void conversation.fetchNextPage()}
            >
              {conversation.isFetchingNextPage ? 'Loading older messages…' : 'Load older messages'}
            </Button>
          </div>
        )}
        {conversation.isFetchNextPageError && (
          <p role="alert" className="text-center text-[13px] text-bad-ink">
            Older messages could not be loaded. {describeError(conversation.error)}
          </p>
        )}
        {isEmpty && intro}
        {messages.map((message) => (
          <ThreadMessage key={message.id} message={message} context={context} />
        ))}
        {outbox.outbox.map((message) => (
          <OutgoingBubble
            key={message.localId}
            message={message}
            author={user?.display_name ?? 'You'}
            onRetry={() => {
              outbox.retry(message);
            }}
            onDiscard={() => {
              outbox.discard(message);
            }}
          />
        ))}
        {activeRun && conversation.activeRun && (
          <ActiveRunProgress run={activeRun} canEdit={canEdit === true} driver={driver} />
        )}
        {showSetup && !isEmpty && intro}
      </>
    );
  }

  return (
    <>
      <ChatLayout
        scrollerRef={scroller}
        contentRef={threadContent}
        thread={thread}
        composer={
          <Composer
            projectId={projectId}
            canEdit={canEdit}
            maxChars={project?.limits.conversation.max_message_chars ?? null}
            answering={answering}
            onStopAnswering={() => {
              setAnsweringRef(null);
            }}
            workingRunId={working?.id ?? null}
            changeRequest={changeRequestOption(
              scope?.state,
              baseline ? { versionId: baseline.id, contentHash: baseline.content_hash } : null,
            )}
            onSend={(text, kind) => {
              outbox.send(
                text,
                kind,
                kind === 'change_request' && baseline
                  ? { versionId: baseline.id, contentHash: baseline.content_hash }
                  : null,
              );
            }}
            onSubmitted={scrollToLatest}
            inputRef={composerInput}
          />
        }
      />
      {evidence && (
        <ChatEvidenceSheet
          projectId={projectId}
          evidence={evidence}
          messages={messages}
          onClose={() => {
            showEvidence(null);
          }}
        />
      )}
    </>
  );
}
