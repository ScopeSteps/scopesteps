import { useState } from 'react';
import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { SegmentedControl } from '@/components/SegmentedControl';
import { describeError } from '@/lib/apiError';

import { DecisionRows } from './DecisionRows';
import { EvidenceSheet } from './EvidenceSheet';
import { ScopeRows } from './ScopeRows';
import { StoryRow } from './StoryRow';
import { attention, claimParam, isUnderReview, parseClaimParam } from './types';
import type { BacklogItem, BacklogVersion, ClaimRef } from './types';
import { useBacklogVersion } from './useBacklogVersion';

type Filter = 'all' | 'attention';

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Needs attention' },
] as const;

const GROUP_HEADING =
  'flex gap-2 px-0.5 pt-2 text-xs font-semibold tracking-[0.06em] text-subtle uppercase';

function heading(version: BacklogVersion): { title: string; note: string } {
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
      return { title: 'Approved version', note: 'Approved · read-only' };
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>('all');
  // Rows the reviewer opened or closed; the rest follow whether they need attention.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const openClaim = parseClaimParam(searchParams.get('evidence'));

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

  const reviewing = isUnderReview(version);
  const onlyAttention = reviewing && filter === 'attention';
  const epics = version.items.filter((item) => item.kind === 'epic');
  const stories = version.items.filter((item) => item.kind === 'story');
  const { blocked, suggestions } = attention(version.blockers);
  const attentionCount = blocked + suggestions;
  const decisions = onlyAttention
    ? version.decisions.filter((decision) => decision.status !== 'answered')
    : version.decisions;
  const { title, note } = heading(version);

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
        <h2 id="backlog-heading" className="text-[17px] font-semibold">
          {title}
        </h2>
        <span className="text-xs text-subtle">
          {plural(epics.length, 'epic')}, {plural(stories.length, 'story', 'stories')}
        </span>
      </div>
      <p className="-mt-2 text-xs text-subtle">
        {note}
        {version.state === 'approved' && (
          <>
            {' · '}
            <span className="font-mono tabular-nums" title={version.content_hash}>
              {version.content_hash.slice(0, 4)}…{version.content_hash.slice(-4)}
            </span>
          </>
        )}
      </p>

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
                  key={story.id}
                  projectId={projectId}
                  story={story}
                  decisions={version.decisions}
                  expanded={toggled[story.id] ?? (reviewing && needsAttention(story))}
                  onToggle={() => {
                    setToggled((current) => ({
                      ...current,
                      [story.id]: !(current[story.id] ?? (reviewing && needsAttention(story))),
                    }));
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
