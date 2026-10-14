import { useState } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { SegmentedControl } from '@/components/SegmentedControl';
import { useToast } from '@/components/toastContext';
import { useCanApprove, useCanEdit, useCurrentUser } from '@/features/identity';
import { useProject } from '@/features/projects';
import { ApiError, describeError } from '@/lib/apiError';

import { ApproveModal } from './ApproveModal';
import { DecisionRows } from './DecisionRows';
import type { DraftControls } from './draftControls';
import { EvidenceSheet } from './EvidenceSheet';
import { ExportButton } from './ExportButton';
import { ScopeRows } from './ScopeRows';
import { StoryRow } from './StoryRow';
import { attention, claimParam, isStale, isUnderReview, parseClaimParam, shortHash } from './types';
import type { BacklogItem, BacklogVersion, ClaimRef, ScopeStatus } from './types';
import { useBacklogVersion } from './useBacklogVersion';
import { useDraftCommands } from './useDraftCommands';
import { VersionSelect } from './VersionSelect';

type Filter = 'all' | 'attention';

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Needs attention' },
] as const;

const GROUP_HEADING =
  'flex gap-2 px-0.5 pt-2 text-xs font-semibold tracking-[0.06em] text-subtle uppercase';

function heading(
  version: BacklogVersion,
  status: ScopeStatus | undefined,
): { title: string; note: string } {
  const revision = `r${String(version.revision)}`;
  switch (version.state) {
    case 'draft':
      return {
        title: `Draft ${revision}`,
        note: `Draft revision ${revision}. Nothing is final until it’s approved.`,
      };
    case 'in_review':
      return {
        title: `Draft ${revision} · in review`,
        note: `Revision ${revision} is in review. Nothing is final until it’s approved.`,
      };
    case 'approved':
      return {
        title:
          version.id === status?.baseline_version_id && status.baseline_version !== null
            ? `Baseline v${String(status.baseline_version)}`
            : 'Approved version',
        note: 'Approved · read-only. Later changes start a new draft; this version never changes.',
      };
    case 'rejected':
      return { title: `Draft ${revision} · rejected`, note: `Revision ${revision} was rejected.` };
  }
}

function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${String(count)} ${count === 1 ? noun : many}`;
}

function needsAttention(story: BacklogItem): boolean {
  return story.blockers.length > 0;
}

interface BacklogViewProps {
  projectId: string;
  versionId: string;
}

export function BacklogView({ projectId, versionId }: BacklogViewProps) {
  const { data: version, error, isPending, refetch } = useBacklogVersion(projectId, versionId);

  if (isPending) {
    return (
      <p role="status" className="text-subtle">
        Loading the backlog…
      </p>
    );
  }
  if (error) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the backlog. {describeError(error)}
      </Banner>
    );
  }
  return <VersionView key={version.id} projectId={projectId} version={version} reload={refetch} />;
}

interface VersionViewProps {
  projectId: string;
  version: BacklogVersion;
  reload: () => Promise<unknown>;
}

function VersionView({ projectId, version, reload }: VersionViewProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>('all');
  // Rows the reviewer opened or closed; the rest follow whether they need attention.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const [editingId, setEditingId] = useState<string | null>(null);
  // Bumped on reload, so open answer forms start again from what the server now holds.
  const [reloads, setReloads] = useState(0);
  const [approving, setApproving] = useState(false);
  const commands = useDraftCommands(projectId, version);
  const canEdit = useCanEdit(projectId);
  const canApprove = useCanApprove(projectId);
  const { data: user } = useCurrentUser();
  const { data: project } = useProject(projectId);
  const showToast = useToast();
  const openClaim = parseClaimParam(searchParams.get('evidence'));
  const status = project?.status;
  const isDraft = version.state === 'draft';
  const draft: DraftControls | null =
    isDraft && (canEdit || canApprove) ? { commands, canEdit, canAnswer: true } : null;
  const stale = isStale(commands.error) ? commands.error : null;
  const baselineNumber = (status?.baseline_version ?? 0) + 1;

  async function reloadDraft() {
    commands.reset();
    setEditingId(null);
    setReloads((count) => count + 1);
    await reload();
  }

  function selectVersion(id: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete('run');
      next.delete('evidence');
      next.set('version', id);
      return next;
    });
  }

  function showEvidence(claim: ClaimRef | null) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (claim) {
        next.set('evidence', claimParam(claim));
      } else {
        next.delete('evidence');
      }
      return next;
    });
  }

  const reviewing = isUnderReview(version);
  const onlyAttention = reviewing && filter === 'attention';
  const epics = version.items.filter((item) => item.kind === 'epic');
  const stories = version.items.filter((item) => item.kind === 'story');
  const { blocked, suggestions } = attention(version.blockers);
  const attentionCount = blocked + suggestions;
  const decisions = onlyAttention
    ? version.decisions.filter((decision) => decision.status !== 'answered')
    : version.decisions;
  const { title, note } = heading(version, status);

  const groups = epics
    .map((epic) => ({
      epic,
      stories: stories.filter(
        (story) => story.parent_id === epic.id && (!onlyAttention || needsAttention(story)),
      ),
    }))
    .filter((group) => !onlyAttention || group.stories.length > 0);
  const showScope = !onlyAttention && version.out_of_scope.length > 0;
  const nothingShown = groups.length === 0 && decisions.length === 0 && !showScope;

  return (
    <section aria-labelledby="backlog-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="backlog-heading" className="text-[17px] font-semibold">
            {title}
          </h2>
          {status && (
            <VersionSelect
              projectId={projectId}
              version={version}
              status={status}
              onSelect={selectVersion}
            />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-subtle">
            {plural(epics.length, 'epic')}, {plural(stories.length, 'story', 'stories')}
          </span>
          {version.state === 'approved' && (
            <ExportButton projectId={projectId} versionId={version.id} />
          )}
          {isDraft &&
            user &&
            (canApprove ? (
              <Button
                variant="primary"
                disabled={stale !== null}
                onClick={() => {
                  setApproving(true);
                }}
              >
                Approve as v{baselineNumber}…
              </Button>
            ) : (
              <span className="text-xs text-subtle">Approval needs a Product owner</span>
            ))}
        </div>
      </div>
      <p className="-mt-2 text-xs text-subtle">
        {note}
        {version.state === 'approved' && (
          <>
            {' · '}
            <span className="font-mono tabular-nums" title={version.content_hash}>
              {shortHash(version.content_hash)}
            </span>
          </>
        )}
      </p>

      {stale && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void reloadDraft()}>
              Reload
            </Button>
          }
        >
          {stale instanceof ApiError && stale.code === 'VERSION_NOT_DRAFT'
            ? 'This version was approved or rejected meanwhile, so it can no longer change.'
            : 'Someone else changed this draft after you opened it.'}{' '}
          Your change was not saved. Reload to see the latest revision and review it again.
        </Banner>
      )}

      {reviewing && attentionCount > 0 && (
        <Banner tone="warn" role="status">
          <strong className="font-semibold">
            {plural(attentionCount, 'item')} {attentionCount === 1 ? 'needs' : 'need'} attention
          </strong>{' '}
          before approval:{' '}
          {[
            blocked > 0 && `${String(blocked)} blocked by open decisions`,
            suggestions > 0 && `${plural(suggestions, 'agent suggestion')} to review`,
          ]
            .filter(Boolean)
            .join(', ')}
          .
        </Banner>
      )}
      {reviewing && (
        <SegmentedControl
          label="Filter stories"
          options={FILTERS}
          value={filter}
          onChange={setFilter}
        />
      )}

      {epics.length === 0 && (
        <p className="text-subtle">
          The sources confirm no scope yet, so this backlog has no epics or stories.
        </p>
      )}
      {groups.map(({ epic, stories: epicStories }) => (
        <section key={epic.id} aria-labelledby={`epic-${epic.id}`} className="flex flex-col gap-2">
          <h3 id={`epic-${epic.id}`} className={GROUP_HEADING}>
            <span className="sr-only">Epic:</span> {epic.title}
          </h3>
          {epic.description && <p className="px-0.5 text-[13px] text-muted">{epic.description}</p>}
          {epicStories.length === 0 ? (
            <p className="px-0.5 text-xs text-subtle">No stories in this epic yet.</p>
          ) : (
            <ul className="m-0 list-none overflow-hidden rounded-xl border border-line bg-surface p-0">
              {epicStories.map((story) => (
                <StoryRow
                  key={`${story.id}-${String(reloads)}`}
                  draft={draft}
                  editing={editingId === story.id}
                  onEditingChange={(editing) => {
                    setEditingId(editing ? story.id : null);
                  }}
                  projectId={projectId}
                  story={story}
                  decisions={version.decisions}
                  expanded={
                    editingId === story.id ||
                    (toggled[story.id] ?? (reviewing && needsAttention(story)))
                  }
                  onToggle={() => {
                    if (editingId === story.id) {
                      setEditingId(null);
                    }
                    setToggled((current) => ({
                      ...current,
                      [story.id]: !(
                        editingId === story.id ||
                        (current[story.id] ?? (reviewing && needsAttention(story)))
                      ),
                    }));
                  }}
                  onKeepOpen={() => {
                    setToggled((current) => ({ ...current, [story.id]: true }));
                  }}
                  onShowEvidence={showEvidence}
                />
              ))}
            </ul>
          )}
        </section>
      ))}

      {decisions.length > 0 && (
        <section aria-labelledby="decisions-heading" className="flex flex-col gap-2">
          <h3 id="decisions-heading" className={GROUP_HEADING}>
            Decisions
          </h3>
          <DecisionRows
            key={reloads}
            draft={draft}
            projectId={projectId}
            decisions={decisions}
            items={version.items}
            onShowEvidence={showEvidence}
          />
        </section>
      )}

      {showScope && (
        <section aria-labelledby="scope-heading" className="flex flex-col gap-2">
          <h3 id="scope-heading" className={GROUP_HEADING}>
            Out of scope
          </h3>
          <ScopeRows
            projectId={projectId}
            notes={version.out_of_scope}
            onShowEvidence={showEvidence}
          />
        </section>
      )}

      {onlyAttention && nothingShown && (
        <Banner>Nothing here. Everything in this view is resolved.</Banner>
      )}

      {approving && (
        <ApproveModal
          projectId={projectId}
          version={version}
          baselineNumber={baselineNumber}
          onReload={reloadDraft}
          onApproved={(decision) => {
            setApproving(false);
            showToast(
              `Baseline v${String(decision.baseline_version ?? baselineNumber)} saved. It can’t be overwritten.`,
            );
          }}
          onClose={() => {
            setApproving(false);
          }}
        />
      )}

      {openClaim && (
        <EvidenceSheet
          version={version}
          claim={openClaim}
          onClose={() => {
            showEvidence(null);
          }}
        />
      )}
    </section>
  );
}
