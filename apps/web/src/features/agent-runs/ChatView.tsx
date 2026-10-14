import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { useCanEdit } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { Composer } from './Composer';
import { NewChatIntro } from './NewChatIntro';
import { RunEvidenceSheet } from './RunEvidenceSheet';
import { RunThread } from './RunThread';
import { evidenceParam, parseEvidenceParam } from './types';
import type { EvidenceRef } from './types';
import { useRun } from './useRun';
import { useRunDriver } from './useRunDriver';

interface ChatViewProps {
  projectId: string;
  /** The run in the thread, or null for a new chat that offers to start one. */
  runId: string | null;
  onRunSelected: (runId: string | null) => void;
  /** Where the backlog page shows a version, so the thread can link to the draft. */
  backlogHref: (versionId: string) => string;
}

/** The thread and the composer under it, filling the page so the composer stays in view. */
function ChatLayout({ thread, composer }: { thread: ReactNode; composer: ReactNode }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto flex max-w-[760px] flex-col gap-[22px] px-5 pt-7 pb-3 max-wide:px-4">
          {thread}
        </div>
      </div>
      {composer}
    </div>
  );
}

/**
 * The chat with the agent, built from the run's state rather than stored messages: the run
 * starting, the agent's questions, its progress, the draft and anything that went wrong.
 */
export function ChatView({ projectId, runId, onRunSelected, backlogHref }: ChatViewProps) {
  const canEdit = useCanEdit(projectId);
  const composerInput = useRef<HTMLTextAreaElement>(null);

  if (runId === null) {
    return (
      <ChatLayout
        thread={
          <NewChatIntro
            projectId={projectId}
            canEdit={canEdit}
            onRunSelected={onRunSelected}
            backlogHref={backlogHref}
          />
        }
        composer={
          <Composer
            projectId={projectId}
            run={undefined}
            canEdit={canEdit}
            answering={null}
            onStopAnswering={() => undefined}
            inputRef={composerInput}
          />
        }
      />
    );
  }
  return (
    <RunChat
      key={runId}
      projectId={projectId}
      runId={runId}
      canEdit={canEdit}
      onRunSelected={onRunSelected}
      backlogHref={backlogHref}
    />
  );
}

interface RunChatProps extends Omit<ChatViewProps, 'runId'> {
  runId: string;
  canEdit: boolean;
}

function RunChat({ projectId, runId, canEdit, onRunSelected, backlogHref }: RunChatProps) {
  const { data: run, error, isPending, refetch } = useRun(runId, { watch: !canEdit });
  const driver = useRunDriver(run, canEdit);
  const [answeringId, setAnsweringId] = useState<string | null>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const evidence = parseEvidenceParam(searchParams.get('evidence'));

  // A question answered meanwhile (another tab, a refresh) is no longer one to answer.
  const answering =
    run?.questions.find((question) => question.id === answeringId && question.status === 'open') ??
    null;

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

  let thread: ReactNode;
  if (isPending) {
    thread = (
      <p role="status" className="text-subtle">
        Loading the run…
      </p>
    );
  } else if (!run) {
    // A failed background refresh keeps showing the run that is already loaded.
    thread = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <span className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => void refetch()}>
              Try again
            </Button>
            <Button
              size="sm"
              onClick={() => {
                onRunSelected(null);
              }}
            >
              {canEdit ? 'Start a new run' : 'Back to the new chat'}
            </Button>
          </span>
        }
      >
        Could not load the run. {describeError(error)}
      </Banner>
    );
  } else {
    thread = (
      <RunThread
        projectId={projectId}
        run={run}
        canEdit={canEdit}
        driver={driver}
        answeringId={answering?.id ?? null}
        onAnswer={setAnsweringId}
        onShowEvidence={showEvidence}
        onStartNewRun={() => {
          onRunSelected(null);
        }}
        backlogHref={backlogHref}
      />
    );
  }

  return (
    <>
      <ChatLayout
        thread={thread}
        composer={
          <Composer
            projectId={projectId}
            run={run}
            canEdit={canEdit}
            answering={answering}
            onStopAnswering={() => {
              setAnsweringId(null);
            }}
            inputRef={composerInput}
          />
        }
      />
      {run && evidence && (
        <RunEvidenceSheet
          projectId={projectId}
          run={run}
          evidence={evidence}
          onClose={() => {
            showEvidence(null);
          }}
        />
      )}
    </>
  );
}
