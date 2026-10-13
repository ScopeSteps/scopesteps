import { useSearchParams } from 'react-router';

import { describeError } from '@/lib/apiError';

import { DecisionList } from './DecisionList';
import { EvidenceButton } from './EvidenceButton';
import { EvidenceDrawer } from './EvidenceDrawer';
import { StoryCard } from './StoryCard';
import { claimParam, parseClaimParam } from './types';
import type { ClaimRef } from './types';
import { useBacklogVersion } from './useBacklogVersion';

const STATE_LABELS = {
  draft: 'Draft: not approved',
  in_review: 'In review: not approved',
  approved: 'Approved baseline',
  rejected: 'Rejected',
};

interface BacklogViewProps {
  projectId: string;
  versionId: string;
}

export function BacklogView({ projectId, versionId }: BacklogViewProps) {
  const { data: version, error, isPending, refetch } = useBacklogVersion(projectId, versionId);
  const [searchParams, setSearchParams] = useSearchParams();
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
    return <p role="status">Loading the backlog…</p>;
  }
  if (error) {
    return (
      <div role="alert" className="text-sm text-bad-ink">
        <p>Could not load the backlog. {describeError(error)}</p>
        <button type="button" onClick={() => void refetch()} className="mt-2 underline">
          Try again
        </button>
      </div>
    );
  }

  const epics = version.items.filter((item) => item.kind === 'epic');
  const stories = version.items.filter((item) => item.kind === 'story');
  const blockedStories = stories.filter((story) => story.blockers.length > 0).length;

  return (
    <section aria-labelledby="backlog-heading" className="space-y-6">
      <div>
        <h2 id="backlog-heading" className="text-lg font-semibold">
          Backlog
        </h2>
        <p className="mt-1 text-sm">
          <span className="font-medium">{STATE_LABELS[version.state]}</span> · revision{' '}
          {version.revision} · {epics.length} {epics.length === 1 ? 'epic' : 'epics'},{' '}
          {stories.length} {stories.length === 1 ? 'story' : 'stories'}
        </p>
        <p className="mt-1 font-mono text-xs break-all text-muted">Version {version.id}</p>
        <p role="status" className="mt-2 text-sm font-medium">
          {blockedStories === 0
            ? 'No story is blocked.'
            : `${String(blockedStories)} of ${String(stories.length)} stories cannot be approved yet.`}
        </p>
      </div>

      <DecisionList
        decisions={version.decisions}
        items={version.items}
        onShowEvidence={showEvidence}
      />

      {epics.length === 0 && (
        <p className="text-sm text-muted">
          The sources confirm no scope yet, so this backlog has no epics or stories.
        </p>
      )}
      {epics.map((epic) => (
        <section key={epic.id} aria-labelledby={`item-${epic.id}`}>
          <h3 id={`item-${epic.id}`} className="font-semibold">
            <span className="text-xs font-medium text-muted uppercase">Epic</span> {epic.title}
          </h3>
          <p className="mt-1 text-sm">{epic.description}</p>
          <ul className="mt-3 space-y-3">
            {stories
              .filter((story) => story.parent_id === epic.id)
              .map((story) => (
                <StoryCard key={story.id} story={story} onShowEvidence={showEvidence} />
              ))}
          </ul>
        </section>
      ))}

      {version.out_of_scope.length > 0 && (
        <section aria-labelledby="out-of-scope-heading">
          <h3 id="out-of-scope-heading" className="font-semibold">
            Not in this backlog
          </h3>
          <ul className="mt-2 space-y-2 text-sm">
            {version.out_of_scope.map((note, index) => (
              <li key={note.summary}>
                <span className="font-semibold">
                  {note.kind === 'excluded'
                    ? 'Excluded by the sources:'
                    : 'Suggested, not committed:'}
                </span>{' '}
                {note.summary}{' '}
                <EvidenceButton
                  about={note.summary}
                  count={note.evidence.length}
                  onShow={() => {
                    showEvidence({ type: 'scope', index });
                  }}
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {openClaim && (
        <EvidenceDrawer
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
