import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';

import type { CriterionChange, ItemChange } from './types';

const ITEM_DIFF: Record<ItemChange['kind'], DiffKind> = {
  add_item: 'added',
  modify_item: 'changed',
  remove_item: 'removed',
};

const CRITERION_DIFF: Record<CriterionChange['kind'], DiffKind> = {
  added: 'added',
  modified: 'changed',
  removed: 'removed',
};

const FIELD_NAMES: Record<ItemChange['changed_fields'][number], string> = {
  kind: 'kind',
  parent_id: 'epic',
  title: 'title',
  description: 'description',
  assumptions: 'assumptions',
  open_questions: 'open questions',
};

/** One item's change exactly as the server reported it, with its criteria changes beneath. */
export function ChangeRow({ change }: { change: ItemChange }) {
  const item = change.after ?? change.before;
  const fields = change.changed_fields.map((field) => FIELD_NAMES[field]);
  const oldTitle =
    change.changed_fields.includes('title') && change.before ? change.before.title : null;

  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface-2 px-3 py-[9px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <DiffTag kind={ITEM_DIFF[change.kind]} />
        <span className="text-xs font-semibold text-muted">
          {item?.kind === 'epic' ? 'Epic' : 'Story'}
        </span>
        <span>{item?.title}</span>
      </div>
      {fields.length > 0 && (
        <span className="text-xs text-muted">
          Changed: {fields.join(', ')}.{oldTitle !== null && ` Was “${oldTitle}”.`}
        </span>
      )}
      {change.criteria.length > 0 && (
        <ul aria-label="Acceptance criteria changes" className="flex flex-col gap-1">
          {change.criteria.map((criterion) => (
            <li
              key={criterion.criterion_id}
              className="flex flex-wrap items-start gap-1.5 text-[13px]"
            >
              <DiffTag kind={CRITERION_DIFF[criterion.kind]} />
              <span className="min-w-0 flex-1">
                {(criterion.after ?? criterion.before)?.text}
                {criterion.kind === 'modified' && criterion.before && (
                  <span className="block text-xs text-muted">Was “{criterion.before.text}”</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
