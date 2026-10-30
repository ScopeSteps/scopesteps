import { Link } from 'react-router';

import { Card } from '@/components/Card';
import { Tag } from '@/components/Tag';
import { roleLabelOf } from '@/features/identity';

import type { ProjectWork, WorkPage } from './myWork';
import { projectStatusText } from './projectStatusText';

interface MyProjectListProps {
  projects: readonly ProjectWork[];
  pathFor: (projectId: string, page: WorkPage) => string;
}

const SHOWN_ORDER = ['approver', 'editor', 'viewer'] as const;

export function MyProjectList({ projects, pathFor }: MyProjectListProps) {
  return (
    <section aria-labelledby="my-projects-heading" className="flex flex-col gap-3">
      <h2 id="my-projects-heading" className="text-[17px] font-semibold">
        My projects
      </h2>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {projects.map((project) => (
          <li key={project.id}>
            <Card className="sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 flex-col gap-1.5">
                <Link
                  to={pathFor(project.id, 'chat')}
                  className="font-semibold break-words text-accent-ink hover:underline"
                >
                  {project.name}
                </Link>
                <div className="flex flex-wrap items-center gap-1.5">
                  {SHOWN_ORDER.filter((role) => project.roles.includes(role)).map((role) => (
                    <Tag key={role} tone="accent">
                      {roleLabelOf(role)}
                    </Tag>
                  ))}
                  <Tag>{projectStatusText(project.status)}</Tag>
                </div>
              </div>
              <span className="shrink-0 text-[13px] text-muted">
                {project.waiting > 0 ? (
                  <>
                    <span className="font-mono font-semibold text-warn-ink tabular-nums">
                      {project.waiting}
                    </span>{' '}
                    waiting
                  </>
                ) : (
                  'Nothing waiting'
                )}
              </span>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}
