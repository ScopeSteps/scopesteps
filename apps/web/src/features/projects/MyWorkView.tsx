import { useState } from 'react';
import type { ReactNode } from 'react';

import { MyProjectList } from './MyProjectList';
import { projectsWithRole, waitingGroups } from './myWork';
import type { MyWork, SummaryRole, WorkPage } from './myWork';
import { RoleSummary } from './RoleSummary';
import { WaitingForYou } from './WaitingForYou';

interface MyWorkViewProps {
  work: MyWork;
  pathFor: (projectId: string, page: WorkPage) => string;
  newProjectButton: ReactNode;
}

/** The home page: the user's roles, what waits for them and their projects, from `/me/work`. */
export function MyWorkView({ work, pathFor, newProjectButton }: MyWorkViewProps) {
  const [role, setRole] = useState<SummaryRole | null>(null);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <RoleSummary roles={work.roles} selected={role} onSelect={setRole} />
        {newProjectButton}
      </div>
      <WaitingForYou groups={waitingGroups(work)} pathFor={pathFor} />
      <MyProjectList projects={projectsWithRole(work.projects, role)} pathFor={pathFor} />
    </>
  );
}
