import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router';

import { signInPath } from '@/app/paths';
import type { SignInState } from '@/app/SignInPage';
import { CURRENT_USER_KEY, useCurrentUser } from '@/features/identity';
import { ApiError } from '@/lib/apiError';
import { onSessionEnded } from '@/lib/sessionEvents';

/**
 * Keeps the app to signed-in users. When `/me` or any later request finds no session, it sends
 * the user to sign-in, which drops every cached response and returns them here afterwards. While
 * `/me` is loading the shell shows its loading states, never data; another error from `/me` (the
 * API is down) leaves the app in view, whose pages say what failed.
 */
export function SessionGuard() {
  const { error } = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { pathname, search, hash } = useLocation();
  const here = `${pathname}${search}${hash}`;

  useEffect(
    () =>
      onSessionEnded(() => {
        const wasSignedIn = queryClient.getQueryData(CURRENT_USER_KEY) !== undefined;
        const state: SignInState | null = wasSignedIn ? { sessionEnded: true } : null;
        void navigate(signInPath(here), { replace: true, state });
      }),
    [here, navigate, queryClient],
  );

  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to={signInPath(here)} replace />;
  }
  return <Outlet />;
}
