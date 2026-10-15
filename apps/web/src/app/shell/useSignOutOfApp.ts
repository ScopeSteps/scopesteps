import { useNavigate } from 'react-router';

import { SIGN_IN_ROUTE } from '@/app/paths';
import { useSignOut } from '@/features/identity';

/** Signs out and opens sign-in, with no page to return to: the user chose to leave. */
export function useSignOutOfApp() {
  const navigate = useNavigate();
  return useSignOut(() => {
    void navigate(SIGN_IN_ROUTE, { replace: true });
  });
}
