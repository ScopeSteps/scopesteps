import { useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import type { SubmitEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { AuthLayout } from '@/app/AuthLayout';
import { chatPath, signInFor } from '@/app/paths';
import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { TextField } from '@/components/TextField';
import {
  PasswordToggle,
  roleNames,
  useAcceptInvitation,
  useCurrentUser,
  useInvitation,
  useInvitedSignUp,
  useSignOut,
} from '@/features/identity';
import { ApiError, describeError } from '@/lib/apiError';

/**
 * Where an invitation link lands. Signed in with the invited email, the person joins; signed in
 * as someone else, they are asked to switch; signed out with an account, they sign in first;
 * without an account, they create one here and land in the project, signed in.
 */
export function InvitePage() {
  const { token = '' } = useParams();
  const invitation = useInvitation(token);
  const me = useCurrentUser();

  if (invitation.isPending || me.isPending) {
    return (
      <AuthLayout title="Invitation">
        <p role="status" className="text-muted">
          Opening your invitation…
        </p>
      </AuthLayout>
    );
  }
  if (invitation.error) {
    const invalid =
      invitation.error instanceof ApiError && invitation.error.code === 'INVITATION_INVALID';
    return (
      <AuthLayout title={invalid ? 'This invitation no longer works' : 'Invitation'}>
        <p role="alert" className="text-muted">
          {describeError(invitation.error)}
        </p>
        <Link className="font-semibold text-accent-ink underline" to="/">
          Go to ScopeSteps
        </Link>
      </AuthLayout>
    );
  }

  const offer = invitation.data;
  const signedInAs = me.data?.email ?? null;
  const title = `${offer.invited_by_name || 'Someone'} invited you to ${offer.project_name}`;
  const intro = (
    <>
      You would join as <strong className="text-fg">{roleNames(offer.roles)}</strong>. The
      invitation is for <strong className="break-all text-fg">{offer.email}</strong>.
    </>
  );

  if (signedInAs !== null && signedInAs === offer.email) {
    return (
      <AuthLayout title={title} intro={intro}>
        <Join token={token} />
      </AuthLayout>
    );
  }
  if (signedInAs !== null) {
    return (
      <AuthLayout title={title} intro={intro}>
        <SwitchAccount signedInAs={signedInAs} invitedEmail={offer.email} token={token} />
      </AuthLayout>
    );
  }
  if (offer.has_account) {
    return (
      <AuthLayout title={title} intro={intro}>
        <p className="text-muted">Sign in with that email to join the project.</p>
        <ButtonLink variant="primary" to={signInFor(offer.email, `/invite/${token}`)}>
          Sign in to join
        </ButtonLink>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title={title} intro={intro}>
      <CreateAccount token={token} email={offer.email} />
    </AuthLayout>
  );
}

function Join({ token }: { token: string }) {
  const accept = useAcceptInvitation(token);
  const navigate = useNavigate();
  return (
    <div className="flex flex-col gap-3">
      <Button
        variant="primary"
        className="min-h-[42px]"
        disabled={accept.isPending}
        onClick={() => {
          accept.mutate(undefined, {
            onSuccess: (joined) => {
              void navigate(chatPath(joined.project_id), { replace: true });
            },
          });
        }}
      >
        {accept.isPending ? 'Joining…' : 'Join the project'}
      </Button>
      {accept.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(accept.error)}
        </p>
      )}
    </div>
  );
}

function SwitchAccount({
  signedInAs,
  invitedEmail,
  token,
}: {
  signedInAs: string;
  invitedEmail: string;
  token: string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const signOut = useSignOut(() => {
    queryClient.clear();
    void navigate(signInFor(invitedEmail, `/invite/${token}`), { replace: true });
  });
  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted">
        You are signed in as <strong className="break-all text-fg">{signedInAs}</strong>. Sign out,
        then sign in with the invited email to join.
      </p>
      <Button
        variant="primary"
        className="min-h-[42px]"
        disabled={signOut.isPending}
        onClick={() => {
          signOut.mutate();
        }}
      >
        {signOut.isPending ? 'Signing out…' : 'Sign out and sign in'}
      </Button>
      {signOut.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(signOut.error)}
        </p>
      )}
    </div>
  );
}

function CreateAccount({ token, email }: { token: string; email: string }) {
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [passwordShown, setPasswordShown] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const problemId = useId();
  const signUp = useInvitedSignUp(token);
  const navigate = useNavigate();

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (signUp.isPending) {
      return;
    }
    if (name.trim() === '' || password === '') {
      setProblem('Enter your name and choose a password.');
      return;
    }
    setProblem(null);
    signUp.mutate(
      { display_name: name, password },
      {
        onSuccess: (joined) => {
          void navigate(chatPath(joined.project_id), { replace: true });
        },
        onError: (error) => {
          setProblem(describeError(error));
        },
      },
    );
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      <h2 className="text-base font-semibold">Create your account</h2>
      <TextField label="Email" type="email" value={email} readOnly />
      <TextField
        label="Name"
        autoComplete="name"
        value={name}
        onChange={setName}
        describedBy={problem ? problemId : undefined}
        focusOnMount
      />
      <TextField
        label="Password"
        type={passwordShown ? 'text' : 'password'}
        autoComplete="new-password"
        value={password}
        onChange={setPassword}
        help="A long passphrase is strongest and easiest to remember."
        describedBy={problem ? problemId : undefined}
        trailing={
          <PasswordToggle
            shown={passwordShown}
            onToggle={() => {
              setPasswordShown((shown) => !shown);
            }}
          />
        }
      />
      <p id={problemId} role="alert" className="text-[13px] text-bad-ink empty:hidden">
        {problem}
      </p>
      <Button
        type="submit"
        variant="primary"
        aria-disabled={signUp.isPending}
        className="min-h-[42px] aria-disabled:cursor-not-allowed aria-disabled:opacity-45"
      >
        {signUp.isPending ? 'Joining…' : 'Create account and join'}
      </Button>
    </form>
  );
}
