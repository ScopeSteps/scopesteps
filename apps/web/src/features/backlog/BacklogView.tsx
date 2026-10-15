import { useState } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { SegmentedControl } from '@/components/SegmentedControl';
import { useToast } from '@/components/toastContext';
import { changeRequestName } from '@/features/change-control';
import { useCanApprove, useCanEdit, useCurrentUser } from '@/features/identity';
import { useProject } from '@/features/projects';
import { ApiError, describeError } from '@/lib/apiError';

import { ApproveModal } from './ApproveModal';
import { candidateName, diffByItem, exclusionOutcome, removedItems } from './candidate';
import { DecisionRows } from './DecisionRows';
import type { DraftControls } from './draftControls';
import { EvidenceSheet } from './EvidenceSheet';
import { ExportButton } from './ExportButton';
import { ScopeDecisionCard } from './ScopeDecisionCard';
import { ScopeRows } from './ScopeRows';
import { StoryRow } from './StoryRow';
import { ApprovalNote } from './ApprovalNote';
import { attention, claimParam, isStale, isUnderReview, parseClaimParam } from './types';
import type { BacklogItem, BacklogVersion, ClaimRef } from './types';
import { useBacklogVersion } from './useBacklogVersion';
import { useCandidate } from './useCandidate';
import { useDraftCommands } from './useDraftCommands';
import { useVersionHistory } from './useVersionHistory';
import { VersionSelect } from './VersionSelect';

type Filter = 'all' | 'attention' | 'changes';

const FILTERS: readonly { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Needs attention' },
];

const CANDIDATE_FILTERS: readonly { value: Filter; label: string }[] = [
  ...FILTERS,
  { value: 'changes', label: 'Changes only' },
];

const GROUP_HEADING =
  'flex gap-2 px-0.5 pt-2 text-xs font-semibold tracking-[0.06em] text-subtle uppercase';

interface CandidateOrigin {
  /** The baseline number the candidate was compared with. */
  baseNumber: number | null;
  /** The change request that proposed it. */
  requestNumber: number | null;
}

function heading(
  version: BacklogVersion,
  number: number | null,
  candidate: CandidateOrigin,
): { title: string; note: string } {
  const revision = `r${String(version.revision)}`;
  switch (version.state) {
    case 'draft':
      return {
        title: `Draft ${revision}`,
        note: `Draft revision ${revision}. Nothing is final until it’s approved.`,
      };
    case 'in_review': {
      const base =
        candidate.baseNumber === null ? 'its baseline' : `v${String(candidate.baseNumber)}`;
      const proposer =
        candidate.requestNumber === null
          ? 'Proposed by a change request'
          : `Proposed by ${changeRequestName(candidate.requestNumber)}`;
      return {
        title: `${candidateName(candidate.baseNumber)} (in review)`,
        note: `${proposer}, compared with ${base}. ${base === 'its baseline' ? 'The baseline' : base} stays unchanged unless this is approved.`,
      };
    }
    case 'approved':
      return {
        title: number === null ? 'Approved version' : `Baseline v${String(number)}`,
        note: 'Later changes start a new draft; this version never changes.',
      };
    case 'rejected':
      return { title: `Draft ${revision} · rejected`, note: `Revision ${revision} was rejected.` };
  }
}

/** What a change candidate does to an epic; nothing when it is unchanged or not a candidate. */
function EpicDiff({ kind }: { kind: DiffKind | null | undefined }) {
  return kind ? <DiffTag kind={kind} /> : null;
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
  const history = useVersionHistory(projectId);
  const openClaim = parseClaimParam(searchParams.get('evidence'));
  const candidate = useCandidate(version);
  const changeSet = candidate.changeSet.data;
  const diffs = changeSet ? diffByItem(changeSet) : null;
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
  const onlyChanges = diffs !== null && filter === 'changes';
  // A candidate also lists what it removes, in the epic it was in, so every change shows.
  const removed = changeSet ? removedItems(changeSet) : [];
  const shownItems = [...version.items, ...removed];
  const epics = shownItems.filter((item) => item.kind === 'epic');
  const stories = shownItems.filter((item) => item.kind === 'story');
  const countedEpics = version.items.filter((item) => item.kind === 'epic');
  const countedStories = version.items.filter((item) => item.kind === 'story');
  const diffOf = (item: BacklogItem) => (diffs ? (diffs.get(item.id) ?? null) : undefined);
  const { blocked, suggestions } = attention(version.blockers);
  const attentionCount = blocked + suggestions;
  const scopeDecisions = version.decisions.filter((decision) => decision.kind === 'scope_reversal');
  const otherDecisions = version.decisions.filter((decision) => decision.kind !== 'scope_reversal');
  const decisions = onlyChanges
    ? []
    : onlyAttention
      ? otherDecisions.filter((decision) => decision.status !== 'answered')
      : otherDecisions;
  const isBaseline = version.id === status?.baseline_version_id;
  const listed = history.data?.find((summary) => summary.id === version.id);
  const number = listed?.number ?? (isBaseline ? (status.baseline_version ?? null) : null);
  const { title, note } = heading(version, number, {
    baseNumber: candidate.request.data?.base_version_number ?? status?.baseline_version ?? null,
    requestNumber: candidate.request.data?.number ?? null,
  });

  const groups = epics
    .map((epic) => ({
      epic,
      stories: stories.filter(
        (story) =>
          story.parent_id === epic.id &&
          (!onlyAttention || needsAttention(story)) &&
          (!onlyChanges || Boolean(diffOf(story))),
      ),
    }))
    .filter(
      (group) =>
        (!onlyAttention || group.stories.length > 0) &&
        (!onlyChanges || group.stories.length > 0 || Boolean(diffOf(group.epic))),
    );
  const outcome = changeSet ? exclusionOutcome(changeSet, version.decisions) : 'pending';
  const exclusionDecision = changeSet?.scope_decisions.find(
    (reversal) => reversal.reverses === 'exclusion',
  );
  const removedExclusions = (changeSet?.removed_exclusions ?? []).map((exclusion) => ({
    summary: exclusion.summary,
    evidence: exclusion.evidence,
    outcome,
    onOpen: () => {
      if (exclusionDecision) {
        showEvidence({ type: 'decision', id: exclusionDecision.decision_id });
      }
    },
  }));
  const showScope =
    !onlyAttention &&
    (onlyChanges
      ? removedExclusions.length > 0
      : version.out_of_scope.length + removedExclusions.length > 0);
  const nothingShown = groups.length === 0 && decisions.length === 0 && !showScope;

  return (
    <section aria-labelledby="backlog-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="backlog-heading" className="text-[17px] font-semibold">
            {title}
          </h2>
          <VersionSelect
            projectId={projectId}
            version={version}
            status={status}
            onSelect={selectVersion}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-subtle">
            {plural(countedEpics.length, 'epic')},{' '}
            {plural(countedStories.length, 'story', 'stories')}
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
      {version.state === 'approved' ? (
        <ApprovalNote
          projectId={projectId}
          version={version}
          approval={listed?.decision ?? null}
          baseline={isBaseline ? null : (status?.baseline_version ?? null)}
          note={note}
        />
      ) : (
        <p className="-mt-2 text-xs text-subtle">{note}</p>
      )}

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
      {candidate.changeSet.isError && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void candidate.changeSet.refetch()}>
              Try again
            </Button>
          }
        >
          Could not load what this candidate changes. {describeError(candidate.changeSet.error)}
        </Banner>
      )}

      {scopeDecisions.length > 0 && !onlyChanges && (
        <section aria-labelledby="scope-decisions-heading" className="flex flex-col gap-2">
          <h3 id="scope-decisions-heading" className={GROUP_HEADING}>
            Scope decisions
          </h3>
          {scopeDecisions.map((decision) => (
            <ScopeDecisionCard
              key={decision.id}
              projectId={projectId}
              version={version}
              decision={decision}
              reversal={changeSet?.scope_decisions.find(
                (reversal) => reversal.decision_id === decision.id,
              )}
              onShowEvidence={(id) => {
                showEvidence({ type: 'decision', id });
              }}
            />
          ))}
        </section>
      )}

      {reviewing && (
        <SegmentedControl
          label="Filter stories"
          options={diffs ? CANDIDATE_FILTERS : FILTERS}
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
            <EpicDiff kind={diffOf(epic)} />
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
                  diff={diffOf(story)}
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
            notes={onlyChanges ? [] : version.out_of_scope}
            removed={removedExclusions}
            onShowEvidence={showEvidence}
          />
        </section>
      )}

      {(onlyAttention || onlyChanges) && nothingShown && (
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
