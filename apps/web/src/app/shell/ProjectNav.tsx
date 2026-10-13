import { NavLink } from 'react-router';

import { Badge } from '@/components/Badge';
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
}

/** One entry per screen that works today. A screen joins the list with its API. */
export function ProjectNav({ project, onNavigate }: ProjectNavProps) {
  const items: NavItem[] = [
    {
      label: 'Backlog',
      icon: 'backlog',
      to: project.backlogPath,
      attention: project.backlogAttention,
    },
    { label: 'Sources', icon: 'sources', to: project.sourcesPath, attention: 0 },
  ];

  return (
    <nav aria-label="Project">
      <ul className="flex flex-col gap-0.5">
        {items.map((item) => (
          <li key={item.label}>
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
                  label={`${String(item.attention)} ${item.attention === 1 ? 'needs' : 'need'} attention`}
                />
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
