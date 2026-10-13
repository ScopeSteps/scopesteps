import { EvidenceButton } from './EvidenceButton';
import { OriginBadge } from './OriginBadge';
import type { BacklogItem, ClaimRef } from './types';

interface StoryCardProps {
  story: BacklogItem;
  onShowEvidence: (claim: ClaimRef) => void;
}

export function StoryCard({ story, onShowEvidence }: StoryCardProps) {
  const headingId = `item-${story.id}`;
  return (
    <li className="rounded border border-gray-300 p-4">
      <article aria-labelledby={headingId}>
        <h4 id={headingId} className="font-semibold">
          <span className="text-xs font-medium text-gray-600 uppercase">Story</span> {story.title}
        </h4>
        <p className="mt-1 text-sm">{story.description}</p>
        <p className="mt-1 font-mono text-xs break-all text-gray-600">Item {story.id}</p>
        {story.human_edited && <p className="mt-1 text-xs font-medium">Edited by a reviewer</p>}

        {story.blockers.length > 0 && (
          <ul
            aria-label={`Blockers for ${story.title}`}
            className="mt-3 space-y-1 rounded border border-red-700 bg-red-50 p-2 text-sm text-red-900"
          >
            {story.blockers.map((blocker) => (
              <li key={`${blocker.code}-${blocker.decision_id ?? blocker.criterion_id ?? ''}`}>
                <span className="font-semibold">Blocker:</span> {blocker.message}
              </li>
            ))}
          </ul>
        )}

        <h5 className="mt-3 text-sm font-semibold">Acceptance criteria</h5>
        {story.criteria.length === 0 ? (
          <p className="text-sm text-gray-600">None yet.</p>
        ) : (
          <ul aria-label={`Acceptance criteria for ${story.title}`} className="mt-1 space-y-2">
            {story.criteria.map((criterion) => (
              <li key={criterion.id} className="text-sm">
                <p>{criterion.text}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-2">
                  <OriginBadge origin={criterion.origin} />
                  <EvidenceButton
                    about={criterion.text}
                    count={criterion.evidence.length + criterion.confirmed_by.length}
                    onShow={() => {
                      onShowEvidence({ type: 'criterion', id: criterion.id });
                    }}
                  />
                </p>
              </li>
            ))}
          </ul>
        )}

        {story.assumptions.length > 0 && (
          <ul aria-label={`Assumptions for ${story.title}`} className="mt-3 space-y-1 text-sm">
            {story.assumptions.map((assumption) => (
              <li key={assumption}>
                <span className="font-semibold">Assumption:</span> {assumption}
              </li>
            ))}
          </ul>
        )}
        {story.open_questions.length > 0 && (
          <ul aria-label={`Open questions for ${story.title}`} className="mt-3 space-y-1 text-sm">
            {story.open_questions.map((question) => (
              <li key={question}>
                <span className="font-semibold">Open question:</span> {question}
              </li>
            ))}
          </ul>
        )}
      </article>
    </li>
  );
}
