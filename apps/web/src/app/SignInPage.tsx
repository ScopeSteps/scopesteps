import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useId } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';

import { returnPathParam } from '@/app/paths';
import { Banner } from '@/components/Banner';
import { BrandMark } from '@/components/BrandMark';
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
  const titleId = useId();
  const queryClient = useQueryClient();
  const returnTo = returnPathParam(search);

  // Whoever arrives here, by signing out, an ended session or a link, leaves nothing behind for
  // the next user. The signed-in pages are gone by now, so nothing asks for it again.
  useEffect(() => {
    queryClient.clear();
  }, [queryClient]);

  return (
    <main
      aria-labelledby={titleId}
      className="flex min-h-full items-center justify-center bg-bg px-4 py-8"
    >
      <div className="flex w-[min(400px,100%)] flex-col gap-5">
        <p className="flex items-center justify-center gap-2 text-lg font-bold tracking-[-0.01em]">
          <BrandMark size={28} />
          ScopeSteps
        </p>
        <div className="flex flex-col gap-3.5 rounded-2xl border border-line bg-surface p-6">
          <div className="flex flex-col gap-1">
            <h1 id={titleId} className="text-[22px] font-semibold tracking-[-0.01em]">
              Sign in
            </h1>
            <p className="text-muted">Scope projects with an agent whose work you can check.</p>
          </div>
          {isSignInState(navigationState) && (
            <Banner tone="warn" role="status">
              Your session has ended. Sign in again to continue.
            </Banner>
          )}
          <SignInForm
            onSignedIn={() => {
              void navigate(returnTo, { replace: true });
            }}
          />
        </div>
      </div>
    </main>
  );
}
