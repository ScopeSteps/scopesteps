import { ApiError, describeError } from '@/lib/apiError';

/** Why an upload was refused, and the file it concerns when the API named one. */
export interface UploadRefusal {
  message: string;
  filename: string | null;
}

/**
 * The API's answer to an upload, in its own plain words (each file refusal names the file and
 * says what to do). `details.filename` ties it to a file; a word limit or a lost connection
 * concerns the whole upload.
 */
export function uploadRefusal(error: Error | string | null): UploadRefusal | null {
  if (error === null) {
    return null;
  }
  if (typeof error === 'string') {
    return { message: error, filename: null };
  }
  const filename = error instanceof ApiError ? error.details.filename : undefined;
  return {
    message: describeError(error),
    filename: typeof filename === 'string' ? filename : null,
  };
}
