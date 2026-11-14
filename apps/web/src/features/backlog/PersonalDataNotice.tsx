import { Icon } from '@/components/Icon';

import type { PersonalDataFlag } from './types';

interface PersonalDataNoticeProps {
  /** The item's flags, kept on purpose or not. */
  flags: readonly PersonalDataFlag[];
  /** The item's name as people see it, for the list's label. */
  itemTitle: string;
}

/**
 * Personal data the server's check found in an item, in plain words with what it found. One not
 * yet settled is a warning: edit it out, or an approver keeps it on purpose when approving.
 */
export function PersonalDataNotice({ flags, itemTitle }: PersonalDataNoticeProps) {
  if (flags.length === 0) {
    return null;
  }
  return (
    <ul
      aria-label={`Personal data in ${itemTitle}`}
      className="m-0 flex list-none flex-col gap-1.5 p-0"
    >
      {flags.map((flag) =>
        flag.kept_by === null ? (
          <li
            key={flag.id}
            className="flex gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 py-[9px] text-sm text-warn-ink"
          >
            <span aria-hidden className="mt-0.5 flex-none">
              <Icon name="warn" size={16} />
            </span>
            <span>
              <strong className="font-semibold">Personal data:</strong> {flag.reason} (
              <span className="font-mono break-all">{flag.value}</span>). Edit it out if the team
              does not need it; an Approver can keep it on purpose when approving.
            </span>
          </li>
        ) : (
          <li key={flag.id} className="flex gap-2 px-1 text-xs text-subtle">
            <span aria-hidden className="mt-px flex-none">
              <Icon name="check" size={14} />
            </span>
            <span>
              Kept on purpose: {flag.reason} (
              <span className="font-mono break-all">{flag.value}</span>).
            </span>
          </li>
        ),
      )}
    </ul>
  );
}
