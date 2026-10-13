import type { RouteObject } from 'react-router';

import { BacklogPage } from '@/app/BacklogPage';
import { HomePage } from '@/app/HomePage';
import { NotFoundPage } from '@/app/NotFoundPage';
import { BACKLOG_ROUTE, SOURCES_ROUTE } from '@/app/paths';
import { AppShell } from '@/app/shell/AppShell';
import { SourcesPage } from '@/app/SourcesPage';

/** Every page renders inside the shell. `handle.title` is the heading in the top bar. */
export const routes: RouteObject[] = [
  {
    Component: AppShell,
    children: [
      { path: '/', Component: HomePage, handle: { title: 'ScopeSteps' } },
      {
        path: BACKLOG_ROUTE,
        Component: BacklogPage,
        handle: { title: 'Backlog' },
      },
      {
        path: SOURCES_ROUTE,
        Component: SourcesPage,
        handle: { title: 'Sources' },
      },
      { path: '*', Component: NotFoundPage, handle: { title: 'Page not found' } },
    ],
  },
];
