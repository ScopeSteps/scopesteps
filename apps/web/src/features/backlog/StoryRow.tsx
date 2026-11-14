import { useId } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { CitationChip } from '@/components/CitationChip';
import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';

import { CriteriaList } from './CriteriaList';
import { DiscussionButton } from './DiscussionButton';
import { DecisionAnswer } from './DecisionAnswer';
import { errorFor, isLocked, isSaving } from './draftControls';
import type { DraftControls } from './draftControls';
import { StoryEditForm } from './StoryEditForm';
import { JiraKeyLink } from '@/features/jira';
import type { JiraLinks } from '@/features/jira';

import { PersonalDataNotice } from './PersonalDataNotice';
import { StoryTasks } from './StoryTasks';
import { attention, isSuggestion, shortId, unsettledFlags } from './types';
import type {
  BacklogItem,
  ClaimRef,
  Decision,
  ItemDiscussions,
  PersonalDataFlag,
  TaskSuggestions,
} from './types';

interface StoryRowProps {
  projectId: string;
  story: BacklogItem;
  decisions: Decision[];
  expanded: boolean;
  onToggle: () => void;
  onShowEvidence: (claim: ClaimRef) => void;
  /** The draft's controls, or null when the version or the reader's role is read-only. */
  draft: DraftControls | null;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
  /** Keeps the row open after the reviewer acts in it, even once it needs no attention. */
  onKeepOpen: () => void;
  /**
   * On a change candidate: what the change does to the story (null when it is unchanged), shown
   * with the story's stable id. Undefined elsewhere.
   */
  diff?: DiffKind | null | undefined;
  discussions?: ItemDiscussions | undefined;
  /** Suggesting tasks with the agent, on a draft an editor can change. */
  taskSuggestions?: TaskSuggestions | undefined;
  /** The Jira issue of the story and its tasks, once published. */
  jiraLinks?: JiraLinks | undefined;
  /** Personal data the server's check found in the story. */
  personalData?: readonly PersonalDataFlag[] | undefined;
}

/** A story as a row that opens to show its text, criteria, blockers and assumptions. */
export function StoryRow({
  projectId,
  story,
  decisions,
  expanded,
  onToggle,
  onShowEvidence,
  draft,
  editing,
  onEditingChange,
  onKeepOpen,
  diff,
  discussions,
  taskSuggestions,
  jiraLinks,
  personalData = [],
}: StoryRowProps) {
  const jira = jiraLinks?.[story.id];
  const bodyId = useId();
  const target = `item:${story.id}`;
  const locked = draft ? isLocked(draft) : true;
  const itemError = draft ? errorFor(draft, target) : null;
  const { blocked, suggestions } = attention(story.blockers);
  const waiting = story.blockers.filter((blocker) => !isSuggestion(blocker));
  const unsettled = unsettledFlags(personalData).length;

  return (
    <li className="border-t border-line first:border-t-0">
      <div className="flex items-center">
        <h5 className="min-w-0 flex-1">
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
            <Tag>Story</Tag>{' '}
            {diff !== undefined && (
              <>
                <span className="font-mono text-xs text-subtle tabular-nums" title={story.id}>
                  {shortId(story.id)}
                </span>{' '}
              </>
            )}
            <span
              className={cx(
                'min-w-0 flex-1 text-sm font-semibold',
                diff === 'removed' && 'text-muted line-through',
              )}
            >
              {story.title}
            </span>{' '}
            <span className="flex flex-wrap gap-1.5">
              {diff && <DiffTag kind={diff} />}
              {blocked > 0 && <Tag tone="bad">{blocked} blocked</Tag>}
              {suggestions > 0 && (
                <Tag tone="warn">
                  {suggestions} {suggestions === 1 ? 'suggestion' : 'suggestions'}
                </Tag>
              )}
              {unsettled > 0 && <Tag tone="warn">Personal data</Tag>}
              {story.human_edited && <Tag>Edited</Tag>}
            </span>
          </button>
        </h5>
        {jira && (
          <span className="pr-1">
            <JiraKeyLink link={jira} />
          </span>
        )}
        {discussions && (
          <span className="pr-2">
            <DiscussionButton item={story} discussions={discussions} />
          </span>
        )}
      </div>
      {expanded && (
        <div
          id={bodyId}
          className="flex flex-col gap-2.5 pt-0.5 pr-3.5 pb-4 pl-[42px] max-wide:pl-3.5"
        >
          {editing && draft ? (
            <StoryEditForm
              story={story}
              saving={isSaving(draft, target)}
              locked={locked}
              error={itemError}
              onSave={(patch) => {
                onKeepOpen();
                draft.commands.send({ type: 'edit', itemId: story.id, patch }, () => {
                  onEditingChange(false);
                });
              }}
              onCancel={() => {
                draft.commands.reset();
                onEditingChange(false);
              }}
            />
          ) : (
            <>
              <p className="whitespace-pre-line text-muted">{story.description}</p>
              <PersonalDataNotice flags={personalData} itemTitle={story.title} />
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
                        {decision && decision.kind !== 'scope_reversal' && draft?.canAnswer && (
                          <DecisionAnswer
                            decision={decision}
                            saving={isSaving(draft, `decision:${decision.id}`)}
                            disabled={locked}
                            error={errorFor(draft, `decision:${decision.id}`)}
                            onAnswer={(answer, onSaved) => {
                              onKeepOpen();
                              draft.commands.send(
                                { type: 'answer', decisionId: decision.id, answer },
                                onSaved,
                              );
                            }}
                          />
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {story.criteria.length === 0 ? (
                <p className="text-xs text-subtle">No acceptance criteria yet.</p>
              ) : (
                <CriteriaList
                  projectId={projectId}
                  item={story}
                  onShowEvidence={onShowEvidence}
                  draft={draft}
                  onReviewed={onKeepOpen}
                />
              )}
              <StoryTasks
                story={story}
                draft={draft}
                suggestions={taskSuggestions}
                onKeepOpen={onKeepOpen}
                jiraLinks={jiraLinks}
              />
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
              {itemError && (
                <Banner tone="bad" role="alert">
                  The change was not saved. {describeError(itemError)}
                </Banner>
              )}
              {draft?.canEdit && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="self-start"
                  disabled={locked}
                  aria-label={`Edit story: ${story.title}`}
                  onClick={() => {
                    draft.commands.reset();
                    onEditingChange(true);
                  }}
                >
                  Edit story
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}
