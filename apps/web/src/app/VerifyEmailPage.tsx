import { useEffect, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { AuthLayout } from '@/app/AuthLayout';
import { SIGN_IN_ROUTE } from '@/app/paths';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { CheckYourEmail, useResendVerification, useVerifyEmail } from '@/features/identity';
import { describeError } from '@/lib/apiError';

/**
 * Where a confirmation link lands: it confirms the address once, signs the person in and opens
 * the home page. A link that no longer works says so and offers a new one.
 */
export function VerifyEmailPage() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const verify = useVerifyEmail();
  const { mutate } = verify;
  // The link works once: confirm it once, even when development mode runs effects twice.
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) {
      return;
    }
    sent.current = true;
    mutate(token, {
      onSuccess: () => {
        void navigate('/', { replace: true });
      },
    });
  }, [mutate, navigate, token]);

  return (
    <AuthLayout title="Confirm your email">
      {verify.error ? (
        <Expired message={describeError(verify.error)} />
      ) : (
        <p role="status" className="text-muted">
          Confirming your email address…
        </p>
      )}
    </AuthLayout>
  );
}

function Expired({ message }: { message: string }) {
  const [email, setEmail] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const resend = useResendVerification();

  if (sentTo !== null) {
    return <CheckYourEmail email={sentTo} />;
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim();
    if (address === '' || resend.isPending) {
      return;
    }
    resend.mutate(address, {
      onSuccess: () => {
        setSentTo(address);
      },
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <p role="alert" className="text-bad-ink">
        {message}
      </p>
      <form noValidate onSubmit={submit} className="flex flex-col gap-3">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={setEmail}
          help="We send a new link if this address has an account waiting to be confirmed."
        />
        {resend.error && (
          <p role="alert" className="text-[13px] text-bad-ink">
            {describeError(resend.error)}
          </p>
        )}
        <Button type="submit" variant="primary" disabled={resend.isPending}>
          {resend.isPending ? 'Sending…' : 'Send a new link'}
        </Button>
      </form>
      <p className="text-[13px] text-muted">
        Already confirmed?{' '}
        <Link className="font-semibold text-accent-ink underline" to={SIGN_IN_ROUTE}>
          Sign in
        </Link>
      </p>
    </div>
  );
}
