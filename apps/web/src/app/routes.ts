import type { RouteObject } from 'react-router';

import { ActivityPage } from '@/app/ActivityPage';
import { BacklogPage } from '@/app/BacklogPage';
import { ChangeRequestsPage } from '@/app/ChangeRequestsPage';
import { ChatPage } from '@/app/ChatPage';
import { HomePage } from '@/app/HomePage';
import { InvitePage } from '@/app/InvitePage';
import { NotFoundPage } from '@/app/NotFoundPage';
import {
  ACTIVITY_ROUTE,
  BACKLOG_ROUTE,
  CHANGES_ROUTE,
  CHAT_ROUTE,
  INVITE_ROUTE,
  PEOPLE_ROUTE,
  SIGN_IN_ROUTE,
  SIGN_UP_ROUTE,
  SOURCES_ROUTE,
  VERIFY_EMAIL_ROUTE,
} from '@/app/paths';
import { PeoplePage } from '@/app/PeoplePage';
import { SessionGuard } from '@/app/SessionGuard';
import { AppShell } from '@/app/shell/AppShell';
import { SignInPage } from '@/app/SignInPage';
import { SignUpPage } from '@/app/SignUpPage';
import { SourcesPage } from '@/app/SourcesPage';
import { VerifyEmailPage } from '@/app/VerifyEmailPage';

/**
 * Signing in, creating an account, confirming its email and opening an invitation stand alone,
 * without a session; every other page needs one and renders inside the shell. `handle.title` is
 * the heading in the top bar.
 */
export const routes: RouteObject[] = [
  { path: SIGN_IN_ROUTE, Component: SignInPage },
  { path: SIGN_UP_ROUTE, Component: SignUpPage },
  { path: VERIFY_EMAIL_ROUTE, Component: VerifyEmailPage },
  { path: INVITE_ROUTE, Component: InvitePage },
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
