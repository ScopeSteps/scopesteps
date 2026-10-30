import { NavLink } from 'react-router';

import { Badge } from '@/components/Badge';
import type { BadgeTone } from '@/components/Badge';
import { Icon } from '@/components/Icon';
import type { IconName } from '@/components/Icon';
import { cx } from '@/lib/cx';

import type { ProjectStatus } from './projectStatus';

interface ProjectNavProps {
  project: ProjectStatus;
  onNavigate: () => void;
}

interface NavItem {
  label: string;
  icon: IconName;
  to: string;
  attention: number;
  /** What the count is, read out with it; "needs attention" unless set. */
  attentionLabel?: (count: number) => string;
  attentionTone?: BadgeTone;
  /** Starts a new group under a divider, as Sources does in the prototype. */
  startsGroup?: boolean;
}

/** One entry per screen that works today. A screen joins the list with its API. */
export function ProjectNav({ project, onNavigate }: ProjectNavProps) {
  const items: NavItem[] = [
    { label: 'Chat', icon: 'chat', to: project.chatPath, attention: project.chatAttention },
    {
      label: 'Backlog',
      icon: 'backlog',
      to: project.backlogPath,
      attention: project.backlogAttention,
    },
    { label: 'Change requests', icon: 'changes', to: project.changesPath, attention: 0 },
    { label: 'Discussion', icon: 'discussion', to: project.discussionPath, attention: 0 },
    {
      label: 'Sources',
      icon: 'sources',
      to: project.sourcesPath,
      attention: 0,
      startsGroup: true,
    },
    {
      label: 'People',
      icon: 'people',
      to: project.peoplePath,
      attention: project.peopleAttention,
      attentionLabel: (count) =>
        `${String(count)} ${count === 1 ? 'speaker' : 'speakers'} to confirm`,
      attentionTone: 'warn',
    },
    { label: 'Activity', icon: 'activity', to: project.activityPath, attention: 0 },
  ];

  return (
    <nav aria-label="Project">
      <ul className="flex flex-col gap-0.5">
        {items.map((item) => (
          <li
            key={item.label}
            className={cx(item.startsGroup && 'mt-2.5 border-t border-line pt-2.5')}
          >
            <NavLink
              to={item.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  'flex min-h-[38px] w-full items-center gap-2.5 rounded-lg border px-2.5',
                  isActive
                    ? 'border-line bg-surface font-semibold text-fg shadow-raised'
                    : 'border-transparent font-medium text-muted hover:bg-hover hover:text-fg',
                )
              }
            >
              <Icon name={item.icon} />
              {/* The space keeps the label and the badge apart in the link's accessible name. */}
              <span>{item.label}</span>{' '}
              <span className="ml-auto flex">
                <Badge
                  count={item.attention}
                  tone={item.attentionTone}
                  label={
                    item.attentionLabel?.(item.attention) ??
                    `${String(item.attention)} ${item.attention === 1 ? 'needs' : 'need'} attention`
                  }
                />
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
