import { Link } from 'react-router';

import { Icon } from '@/components/Icon';

import { hasWaitingWork } from './myWork';
import type { WaitingGroup, WorkPage } from './myWork';

interface WaitingForYouProps {
  groups: readonly WaitingGroup[];
  pathFor: (projectId: string, page: WorkPage) => string;
}

export function WaitingForYou({ groups, pathFor }: WaitingForYouProps) {
  return (
    <section aria-labelledby="waiting-heading" className="flex flex-col gap-3">
      <h2 id="waiting-heading" className="text-[17px] font-semibold">
        Waiting for you
      </h2>
      {!hasWaitingWork(groups) && (
        <p className="flex items-center gap-2 text-muted">
          <Icon name="check" size={16} />
          You&apos;re all caught up.
        </p>
      )}
      {groups.map((group) => (
        <div key={group.role} className="flex flex-col gap-1.5">
          <h3 className="px-0.5 text-xs font-semibold tracking-[0.06em] text-subtle uppercase">
            {group.title}
          </h3>
          <ul className="m-0 flex list-none flex-col overflow-hidden rounded-xl border border-line bg-surface p-0">
            {group.items.map((item) => (
              <li key={item.key} className="border-t border-line first:border-t-0">
                <Link
                  to={pathFor(item.projectId, item.page)}
                  className="flex items-center justify-between gap-3 px-3.5 py-[11px] text-[13px] hover:bg-hover"
                >
                  <span className="min-w-0 break-words">{item.text}</span>
                  <span className="text-subtle">
                    <Icon name="right" size={16} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
