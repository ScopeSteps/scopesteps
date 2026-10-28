import { Link } from 'react-router';

import { AuthLayout } from '@/app/AuthLayout';
import { SIGN_IN_ROUTE } from '@/app/paths';
import { SignUpForm } from '@/features/identity';

/** Anyone can create an account; it signs in once its email is confirmed. */
export function SignUpPage() {
  return (
    <AuthLayout
      title="Create an account"
      intro="Start scoping your own projects, or join one you were invited to."
      footer={
        <>
          Already have an account?{' '}
          <Link className="font-semibold text-accent-ink underline" to={SIGN_IN_ROUTE}>
            Sign in
          </Link>
        </>
      }
    >
      <SignUpForm />
    </AuthLayout>
  );
}
