import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';

import { AuthLayout } from '@/app/AuthLayout';
import { returnPathParam, SIGN_UP_ROUTE } from '@/app/paths';
import { Banner } from '@/components/Banner';
import { SignInForm } from '@/features/identity';

/** Navigation state set when a request found the session gone, to say why sign-in is back. */
export interface SignInState {
  sessionEnded: true;
}

function isSignInState(state: unknown): state is SignInState {
  return typeof state === 'object' && state !== null && 'sessionEnded' in state;
}

/** The page a signed-out visitor sees. It stands outside the shell: nothing to navigate yet. */
export function SignInPage() {
  const [search] = useSearchParams();
  const navigationState: unknown = useLocation().state;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const returnTo = returnPathParam(search);
  const email = search.get('email') ?? '';

  // Whoever arrives here, by signing out, an ended session or a link, leaves nothing behind for
  // the next user. The signed-in pages are gone by now, so nothing asks for it again.
  useEffect(() => {
    queryClient.clear();
  }, [queryClient]);

  return (
    <AuthLayout
      title="Sign in"
      intro="Scope projects with an agent whose work you can check."
      footer={
        <>
          New to ScopeSteps?{' '}
          <Link className="font-semibold text-accent-ink underline" to={SIGN_UP_ROUTE}>
            Create an account
          </Link>
        </>
      }
    >
      {isSignInState(navigationState) && (
        <Banner tone="warn" role="status">
          Your session has ended. Sign in again to continue.
        </Banner>
      )}
      <SignInForm
        initialEmail={email}
        onSignedIn={() => {
          void navigate(returnTo, { replace: true });
        }}
      />
    </AuthLayout>
  );
}
