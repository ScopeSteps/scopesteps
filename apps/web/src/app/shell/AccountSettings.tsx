import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { TextField } from '@/components/TextField';
import { permissionsFor, roleLabelFor, useCurrentUser } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { useSignOutOfApp } from './useSignOutOfApp';

interface AccountSettingsProps {
  /** The project in view, whose role is shown, or null on a page that belongs to no project. */
  projectId: string | null;
}

/** The account the user signed in with, their role in the project, and the way out. */
export function AccountSettings({ projectId }: AccountSettingsProps) {
  const { data: user } = useCurrentUser();
  const signOut = useSignOutOfApp();
  const roles =
    user && projectId
      ? user.memberships
          .filter((membership) => membership.project_id === projectId)
          .map((membership) => membership.role)
      : [];
  const roleLabel = roleLabelFor(roles);
  const permissions = permissionsFor(roles);

  return (
    <>
      <h3 className="text-[15px] font-semibold">Account</h3>
      {user && (
        <TextField
          label="Email"
          value={user.email}
          readOnly
          help="Used to sign in. Ask your workspace admin to change it."
        />
      )}
      {user && projectId && (
        <section aria-labelledby="account-role" className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h4 id="account-role" className="text-[13px] font-semibold">
              Role in this project
            </h4>
            {roleLabel ? <Tag tone="accent">{roleLabel}</Tag> : <Tag>No role</Tag>}
          </div>
          <span className="text-xs text-subtle">
            Roles are assigned by a workspace admin and control what you can change.
          </span>
          {roleLabel && (
            <ul aria-label="What your role allows" className="flex flex-col gap-1 text-sm">
              {permissions.can.map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <Icon name="check" size={14} />
                  {item}
                </li>
              ))}
              {permissions.cannot.map((item) => (
                <li key={item} className="flex items-center gap-2 text-muted">
                  <Icon name="close" size={14} />
                  Can’t {item.charAt(0).toLowerCase() + item.slice(1)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {user && !projectId && (
        <p className="text-sm text-muted">Open a project to see your role and what it allows.</p>
      )}
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
