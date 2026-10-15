import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { TextField } from '@/components/TextField';
import { useCurrentUser } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { useSignOutOfApp } from './useSignOutOfApp';

/** The account the user signed in with, and the way out of it. */
export function AccountSettings() {
  const { data: user } = useCurrentUser();
  const signOut = useSignOutOfApp();

  return (
    <>
      <h3 className="text-[15px] font-semibold">Account</h3>
      {user && <TextField label="Email" value={user.email} readOnly help="Used to sign in." />}
      <div>
        <Button
          aria-disabled={signOut.isPending}
          onClick={() => {
            if (!signOut.isPending) {
              signOut.mutate();
            }
          }}
          className="aria-disabled:cursor-not-allowed aria-disabled:opacity-45"
        >
          <Icon name="logout" size={16} />
          {signOut.isPending ? 'Signing out…' : 'Sign out'}
        </Button>
      </div>
      {signOut.error && (
        <Banner tone="bad" role="alert">
          Could not sign out. {describeError(signOut.error)}
        </Banner>
      )}
    </>
  );
}
