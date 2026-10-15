import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { ApiError, describeError } from '@/lib/apiError';

import { useSignIn } from './useSignIn';

// Format only: whether the account exists and the password is right is the server's call.
const EMAIL_FORMAT = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Field = 'email' | 'password';

interface Problem {
  /** The field the message is about, or null when it is about both, like a refused sign-in. */
  field: Field | null;
  message: string;
}

interface SignInFormProps {
  onSignedIn: () => void;
}

/** Email and password sign-in. The password lives only in this form's state until it is sent. */
export function SignInForm({ onSignedIn }: SignInFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordShown, setPasswordShown] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const problemId = useId();
  const signIn = useSignIn();

  function reportProblem(next: Problem, focus: Field) {
    setProblem(next);
    const control = form.current?.elements.namedItem(focus);
    if (control instanceof HTMLInputElement) {
      control.focus();
    }
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (signIn.isPending) {
      return;
    }
    const address = email.trim();
    if (!EMAIL_FORMAT.test(address)) {
      reportProblem({ field: 'email', message: 'Enter a valid email address.' }, 'email');
      return;
    }
    if (password === '') {
      reportProblem({ field: 'password', message: 'Enter your password.' }, 'password');
      return;
    }
    setProblem(null);
    signIn.mutate(
      { email: address, password },
      {
        onSuccess: () => {
          setPassword('');
          onSignedIn();
        },
        onError: (error) => {
          const refused = error instanceof ApiError && error.status === 401;
          if (refused) {
            setPassword('');
          }
          reportProblem({ field: null, message: describeError(error) }, 'password');
        },
      },
    );
  }

  // A message about one field describes only that field; one about both describes both.
  function describes(field: Field): string | undefined {
    if (problem === null || (problem.field !== null && problem.field !== field)) {
      return undefined;
    }
    return problemId;
  }

  return (
    <form ref={form} noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      <TextField
        label="Email"
        type="email"
        autoComplete="username"
        inputMode="email"
        placeholder="name@example.edu"
        value={email}
        onChange={setEmail}
        name="email"
        invalid={problem?.field === 'email'}
        describedBy={describes('email')}
        focusOnMount
      />
      <TextField
        label="Password"
        type={passwordShown ? 'text' : 'password'}
        autoComplete="current-password"
        value={password}
        onChange={setPassword}
        name="password"
        invalid={problem?.field === 'password'}
        describedBy={describes('password')}
        trailing={
          <button
            type="button"
            aria-pressed={passwordShown}
            aria-label={passwordShown ? 'Hide password' : 'Show password'}
            onClick={() => {
              setPasswordShown((shown) => !shown);
            }}
            className="min-h-7 cursor-pointer rounded-md px-2 text-[13px] font-semibold text-accent-ink"
          >
            {passwordShown ? 'Hide' : 'Show'}
          </button>
        }
      />
      <p id={problemId} role="alert" className="text-[13px] text-bad-ink empty:hidden">
        {problem?.message}
      </p>
      <Button
        type="submit"
        variant="primary"
        aria-disabled={signIn.isPending}
        className="min-h-[42px] aria-disabled:cursor-not-allowed aria-disabled:opacity-45"
      >
        {signIn.isPending ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
}
