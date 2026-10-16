import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { Banner } from '@/components/Banner';
import { BrandMark } from '@/components/BrandMark';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { hasEdits, useBacklogVersion } from '@/features/backlog';
import { useProject } from '@/features/projects';
import { AddSourceButton, formatBytes, plural, useSources } from '@/features/sources';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { EditedDraftWarning } from './EditedDraftWarning';
import { lastRunId, rememberRun } from './lastRun';
import { setupSteps } from './setupSteps';
import type { StepState } from './setupSteps';
import { useStartRun } from './useStartRun';

interface StepProps {
  state: StepState;
  number: number;
  title: string;
  detail: ReactNode;
  action?: ReactNode;
}

function Step({ state, number, title, detail, action }: StepProps) {
  return (
    <li
      aria-current={state === 'active' ? 'step' : undefined}
      className={cx(
        'flex flex-wrap items-center gap-3 rounded-xl border bg-surface px-3.5 py-3',
        state === 'active' ? 'border-accent-line shadow-focus' : 'border-line',
        state === 'todo' && 'opacity-70',
      )}
    >
      <span
        aria-hidden="true"
        className={cx(
          'flex size-[26px] flex-none items-center justify-center rounded-full border text-xs font-bold',
          state === 'done' && 'border-transparent bg-ok-soft text-ok-ink',
          state === 'active' && 'border-accent bg-accent text-accent-fg',
          state === 'todo' && 'border-line-strong text-subtle',
        )}
      >
        {state === 'done' ? <Icon name="check" size={14} /> : number}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <strong className="font-semibold">
          {title}
          {state === 'done' && <span className="sr-only"> (done)</span>}
        </strong>
        <span className="text-xs text-subtle">{detail}</span>
      </span>
      {action}
    </li>
  );
}

interface NewChatIntroProps {
  projectId: string;
  canEdit: boolean;
  onRunSelected: (runId: string) => void;
  /** Where the backlog page shows a version, to review an edited draft before replacing it. */
  backlogHref: (versionId: string) => string;
  /** Scroll to the steps and move focus to them when shown, as after "Start a new run". */
  reveal?: boolean;
}

/** How to get from an empty project to a draft: add sources, start the run, answer. */
export function NewChatIntro({
  projectId,
  canEdit,
  onRunSelected,
  backlogHref,
  reveal = false,
}: NewChatIntroProps) {
  const sectionRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const section = sectionRef.current;
    if (!reveal || !section) {
      return;
    }
    const still =
      typeof window.matchMedia !== 'function' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // jsdom has no layout, so it has no scrollIntoView either.
    if (typeof section.scrollIntoView === 'function') {
      section.scrollIntoView({ block: 'start', behavior: still ? 'auto' : 'smooth' });
    }
    section.focus({ preventScroll: true });
  }, [reveal]);
  const { data: versions, error, isPending, refetch } = useSources(projectId);
  const { data: project, isPending: projectPending } = useProject(projectId);
  const openVersionId = project?.status.open_version_id ?? null;
  const { data: openDraft, isLoading: draftLoading } = useBacklogVersion(projectId, openVersionId);
  const editedDraft = openDraft && hasEdits(openDraft) ? openDraft : null;
  // Until both are known, starting could replace an edited draft without the warning.
  const checkingDraft = projectPending || draftLoading;
  const [confirming, setConfirming] = useState(false);
  const start = useStartRun(projectId);
  // Kept across a retry whose outcome is unknown, so it cannot create a second run.
  const idempotencyKey = useRef<string | null>(null);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);
  const previousRunId = lastRunId(projectId);
  const limits = project?.limits.source;
  const hasSources = versions !== undefined && versions.length > 0;
  const words = versions?.reduce((total, version) => total + version.word_count, 0) ?? 0;
  const steps = setupSteps(hasSources, project?.status);

  function startRun(sourceVersionIds: string[]) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    idempotencyKey.current ??= crypto.randomUUID();
    start.mutate(
      { sourceVersionIds, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (run) => {
          idempotencyKey.current = null;
          rememberRun(projectId, run.id);
          onRunSelected(run.id);
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            idempotencyKey.current = null;
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  }

  let sourcesDetail: ReactNode;
  if (isPending) {
    sourcesDetail = <span role="status">Loading sources…</span>;
  } else if (hasSources) {
    sourcesDetail = `${plural(versions.length, 'source')} added · ${words.toLocaleString()}${limits ? ` of ${limits.max_words.toLocaleString()}` : ''} words`;
  } else {
    sourcesDetail = limits
      ? `TXT or Markdown, up to ${formatBytes(limits.max_bytes)} each`
      : 'TXT or Markdown';
  }

  return (
    <section
      ref={sectionRef}
      tabIndex={-1}
      aria-labelledby="new-chat-heading"
      className="flex flex-col items-center gap-2.5 px-2 pt-6 pb-2 text-center outline-none"
    >
      <span className="flex size-[52px] items-center justify-center rounded-[14px] bg-accent-soft text-fg">
        <BrandMark size={28} />
      </span>
      <h2 id="new-chat-heading" className="text-[22px] font-semibold tracking-[-0.01em]">
        {project ? `New chat for ${project.name}` : 'New chat'}
      </h2>
      <p className="max-w-[52ch] text-muted">
        ScopeSteps reads your sources, asks about anything unclear, and drafts a backlog you
        approve. Here’s how to get started.
      </p>
      {error && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void refetch()}>
              Try again
            </Button>
          }
        >
          Could not load the stored sources. {describeError(error)}
        </Banner>
      )}
      <ol className="m-0 mt-2.5 flex w-full max-w-[560px] list-none flex-col gap-2 p-0 text-left">
        <Step
          state={steps.sources}
          number={1}
          title="Add a project brief and a meeting transcript"
          detail={sourcesDetail}
          action={
            canEdit && (
              <AddSourceButton
                projectId={projectId}
                size="sm"
                variant={hasSources ? 'default' : 'primary'}
                label={hasSources ? 'Add more' : 'Add sources'}
              />
            )
          }
        />
        <Step
          state={steps.run}
          number={2}
          title="Start the agent run"
          detail="The agent works only from your sources and answers"
          action={
            canEdit && (
              <Button
                size="sm"
                variant="primary"
                disabled={!hasSources || start.isPending || checkingDraft}
                onClick={() => {
                  if (editedDraft) {
                    setConfirming(true);
                  } else if (versions) {
                    startRun(versions.map((version) => version.id));
                  }
                }}
              >
                {start.isPending ? 'Starting…' : 'Start run'}
              </Button>
            )
          }
        />
        <Step
          state={steps.review}
          number={3}
          title="Answer questions, then review the draft backlog"
          detail="Nothing is final until a Product owner approves it"
        />
      </ol>
      {start.error && (
        <Banner tone="bad" role="alert">
          The run could not be started. {describeError(start.error)}
        </Banner>
      )}
      {confirming && editedDraft && (
        <EditedDraftWarning
          revision={editedDraft.revision}
          draftHref={backlogHref(editedDraft.id)}
          onStart={() => {
            setConfirming(false);
            if (versions) {
              startRun(versions.map((version) => version.id));
            }
          }}
          onClose={() => {
            setConfirming(false);
          }}
        />
      )}
      {previousRunId && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onRunSelected(previousRunId);
          }}
        >
          Open the last run started in this browser
        </Button>
      )}
    </section>
  );
}
