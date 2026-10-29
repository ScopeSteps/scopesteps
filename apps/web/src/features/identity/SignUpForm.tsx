import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { ApiError, describeError } from '@/lib/apiError';

import { PasswordToggle } from './PasswordToggle';
import { useResendVerification, useSignUp } from './useAccountCommands';

// Format only: whether the address can be used is the server's call, and it never says.
const EMAIL_FORMAT = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Field = 'display_name' | 'email' | 'password';

interface Problem {
  field: Field | null;
  message: string;
}

/** The field a refusal is about, from what the server reports; null for the whole form. */
function fieldOf(error: Error): Field | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  if (error.code === 'PROFILE_INVALID') {
    return 'display_name';
  }
  if (error.code === 'EMAIL_INVALID') {
    return 'email';
  }
  return 'min_length' in error.details ? 'password' : null;
}

/**
 * Name, email and password for a new account. Once sent it says "Check your email", the same
 * whatever the address, and offers to send the link again.
 */
export function SignUpForm() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordShown, setPasswordShown] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const problemId = useId();
  const signUp = useSignUp();

  function reportProblem(next: Problem, focus: Field) {
    setProblem(next);
    const control = form.current?.elements.namedItem(focus);
    if (control instanceof HTMLInputElement) {
      control.focus();
    }
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (signUp.isPending) {
      return;
    }
    const address = email.trim();
    if (name.trim() === '') {
      reportProblem({ field: 'display_name', message: 'Enter your name.' }, 'display_name');
      return;
    }
    if (!EMAIL_FORMAT.test(address)) {
      reportProblem({ field: 'email', message: 'Enter a valid email address.' }, 'email');
      return;
    }
    if (password === '') {
      reportProblem({ field: 'password', message: 'Choose a password.' }, 'password');
      return;
    }
    setProblem(null);
    signUp.mutate(
      { display_name: name, email: address, password },
      {
        onSuccess: () => {
          setPassword('');
          setSentTo(address);
        },
        onError: (error) => {
          const field = fieldOf(error);
          reportProblem({ field, message: describeError(error) }, field ?? 'email');
        },
      },
    );
  }

  if (sentTo !== null) {
    return <CheckYourEmail email={sentTo} />;
  }

  function describes(field: Field): string | undefined {
    return problem !== null && (problem.field === null || problem.field === field)
      ? problemId
      : undefined;
  }

  return (
    <form ref={form} noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      <TextField
        label="Name"
        autoComplete="name"
        value={name}
        onChange={setName}
        name="display_name"
        invalid={problem?.field === 'display_name'}
        describedBy={describes('display_name')}
        focusOnMount
      />
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        inputMode="email"
        placeholder="name@example.edu"
        value={email}
        onChange={setEmail}
        name="email"
        invalid={problem?.field === 'email'}
        describedBy={describes('email')}
      />
      <TextField
        label="Password"
        type={passwordShown ? 'text' : 'password'}
        autoComplete="new-password"
        value={password}
        onChange={setPassword}
        name="password"
        help="A long passphrase is strongest and easiest to remember."
        invalid={problem?.field === 'password'}
        describedBy={describes('password')}
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
        {problem?.message}
      </p>
      <Button
        type="submit"
        variant="primary"
        aria-disabled={signUp.isPending}
        className="min-h-[42px] aria-disabled:cursor-not-allowed aria-disabled:opacity-45"
      >
        {signUp.isPending ? 'Creating your account…' : 'Create account'}
      </Button>
    </form>
  );
}

/** What everyone sees after signing up or asking again, whatever the address. */
export function CheckYourEmail({ email }: { email: string }) {
  const resend = useResendVerification();
  return (
    <div className="flex flex-col gap-3" role="status">
      <h2 className="text-base font-semibold">Check your email</h2>
      <p className="text-muted">
        If <strong className="break-all text-fg">{email}</strong> can be used, we sent it a link to
        confirm the address. Open it to finish. It works once and for a day.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          disabled={resend.isPending}
          onClick={() => {
            resend.mutate(email);
          }}
        >
          {resend.isPending ? 'Sending…' : 'Send the link again'}
        </Button>
        {resend.isSuccess && <span className="text-[13px] text-ok-ink">Sent again.</span>}
      </div>
      {resend.error && (
        <p role="alert" className="text-[13px] text-bad-ink">
          {describeError(resend.error)}
        </p>
      )}
    </div>
  );
}
