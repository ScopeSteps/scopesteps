import { ApiError } from '@/lib/apiError';

/** The API's reason for refusing a project name, shown on the name field. */
export function rejectedName(error: Error | null): string | null {
  return error instanceof ApiError && error.code === 'PROJECT_NAME_INVALID' ? error.message : null;
}

/** Someone renamed the project after this form was opened. */
export function isStaleProject(error: Error | null): boolean {
  return error instanceof ApiError && error.code === 'PROJECT_CHANGED';
}
