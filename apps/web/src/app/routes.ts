import type { RouteObject } from 'react-router';

import { ActivityPage } from '@/app/ActivityPage';
import { BacklogPage } from '@/app/BacklogPage';
import { ChangeRequestsPage } from '@/app/ChangeRequestsPage';
import { ChatPage } from '@/app/ChatPage';
import { HomePage } from '@/app/HomePage';
import { NotFoundPage } from '@/app/NotFoundPage';
import {
  ACTIVITY_ROUTE,
  BACKLOG_ROUTE,
  CHANGES_ROUTE,
  CHAT_ROUTE,
  PEOPLE_ROUTE,
  SIGN_IN_ROUTE,
  SOURCES_ROUTE,
} from '@/app/paths';
import { PeoplePage } from '@/app/PeoplePage';
import { SessionGuard } from '@/app/SessionGuard';
import { AppShell } from '@/app/shell/AppShell';
import { SignInPage } from '@/app/SignInPage';
import { SourcesPage } from '@/app/SourcesPage';

/**
 * Sign-in stands alone; every other page needs a session and renders inside the shell.
 * `handle.title` is the heading in the top bar.
 */
export const routes: RouteObject[] = [
  { path: SIGN_IN_ROUTE, Component: SignInPage },
  {
    Component: SessionGuard,
    children: [
      {
        Component: AppShell,
        children: [
          { path: '/', Component: HomePage, handle: { title: 'ScopeSteps' } },
          { path: CHAT_ROUTE, Component: ChatPage, handle: { title: 'Chat' } },
          {
            path: BACKLOG_ROUTE,
            Component: BacklogPage,
            handle: { title: 'Backlog' },
          },
          {
            path: CHANGES_ROUTE,
            Component: ChangeRequestsPage,
            handle: { title: 'Change requests' },
          },
          {
            path: SOURCES_ROUTE,
            Component: SourcesPage,
            handle: { title: 'Sources' },
          },
          {
            path: PEOPLE_ROUTE,
            Component: PeoplePage,
            handle: { title: 'People' },
          },
          {
            path: ACTIVITY_ROUTE,
            Component: ActivityPage,
            handle: { title: 'Activity' },
          },
          { path: '*', Component: NotFoundPage, handle: { title: 'Page not found' } },
        ],
      },
    ],
  },
];
