import { useId } from 'react';

import { CitationChip } from '@/components/CitationChip';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { cx } from '@/lib/cx';

import { CriterionRow } from './CriterionRow';
import { attention, isSuggestion } from './types';
import type { BacklogItem, ClaimRef, Decision } from './types';

interface StoryRowProps {
  projectId: string;
  story: BacklogItem;
  decisions: Decision[];
  expanded: boolean;
  onToggle: () => void;
  onShowEvidence: (claim: ClaimRef) => void;
}

/** A story as a row that opens to show its text, criteria, blockers and assumptions. */
export function StoryRow({
  projectId,
  story,
  decisions,
  expanded,
  onToggle,
  onShowEvidence,
}: StoryRowProps) {
  const bodyId = useId();
  const { blocked, suggestions } = attention(story.blockers);
  const waiting = story.blockers.filter((blocker) => !isSuggestion(blocker));

  return (
    <li className="border-t border-line first:border-t-0">
      <h4>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={bodyId}
          onClick={onToggle}
          className="flex min-h-12 w-full cursor-pointer flex-wrap items-center gap-2.5 px-3.5 py-2 text-left hover:bg-hover"
        >
          <span
            aria-hidden="true"
            className={cx('text-subtle transition-transform', expanded && 'rotate-90')}
          >
            <Icon name="right" size={16} />
          </span>
          <span className="min-w-0 flex-1 text-sm font-semibold">{story.title}</span>
          <span className="flex flex-wrap gap-1.5">
            {blocked > 0 && <Tag tone="bad">{blocked} blocked</Tag>}
            {suggestions > 0 && (
              <Tag tone="warn">
                {suggestions} {suggestions === 1 ? 'suggestion' : 'suggestions'}
              </Tag>
            )}
            {story.human_edited && <Tag>Edited</Tag>}
          </span>
        </button>
      </h4>
      {expanded && (
        <div
          id={bodyId}
          className="flex flex-col gap-2.5 pt-0.5 pr-3.5 pb-4 pl-[42px] max-wide:pl-3.5"
        >
          <p className="text-muted">{story.description}</p>
          {waiting.length > 0 && (
            <ul
              aria-label={`Blockers for ${story.title}`}
              className="m-0 flex list-none flex-col gap-2.5 p-0"
            >
              {waiting.map((blocker) => {
                const decision = decisions.find(
                  (candidate) => candidate.id === blocker.decision_id,
                );
                return (
                  <li
                    key={`${blocker.code}-${blocker.decision_id ?? ''}`}
                    className="flex flex-col gap-1.5 rounded-lg border border-bad-line bg-bad-soft px-3 py-[9px] text-sm text-bad-ink"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Tag tone="bad">Waiting on a decision</Tag>
                      {decision && (
                        <span className="ml-auto">
                          <CitationChip
                            aria-label={`Evidence for: ${decision.subject}`}
                            onClick={() => {
                              onShowEvidence({ type: 'decision', id: decision.id });
                            }}
                          >
                            Evidence
                          </CitationChip>
                        </span>
                      )}
                    </div>
                    <p>{blocker.message}</p>
                  </li>
                );
              })}
            </ul>
          )}
          {story.criteria.length === 0 ? (
            <p className="text-xs text-subtle">No acceptance criteria yet.</p>
          ) : (
            <ul
              aria-label={`Acceptance criteria for ${story.title}`}
              className="m-0 flex list-none flex-col gap-2.5 p-0"
            >
              {story.criteria.map((criterion) => (
                <CriterionRow
                  key={criterion.id}
                  projectId={projectId}
                  criterion={criterion}
                  onShowEvidence={onShowEvidence}
                />
              ))}
            </ul>
          )}
          {story.assumptions.length > 0 && (
            <ul
              aria-label={`Assumptions for ${story.title}`}
              className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]"
            >
              {story.assumptions.map((assumption) => (
                <li key={assumption}>
                  <span className="font-semibold">Assumption:</span> {assumption}
                </li>
              ))}
            </ul>
          )}
          {story.open_questions.length > 0 && (
            <ul
              aria-label={`Open questions for ${story.title}`}
              className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]"
            >
              {story.open_questions.map((question) => (
                <li key={question}>
                  <span className="font-semibold">Open question:</span> {question}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
