import type { components } from '@scopesteps/api-client';

type ErrorBody = components['schemas']['ErrorResponse'];

/** A failure the API reported in its error envelope. `message` is written for the user. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly details: ErrorBody['details'];

  constructor(status: number, body: ErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.retryable = body.retryable;
    this.details = body.details;
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    'code' in value &&
    typeof value.code === 'string' &&
    'message' in value &&
    typeof value.message === 'string' &&
    'retryable' in value &&
    typeof value.retryable === 'boolean' &&
    'details' in value &&
    typeof value.details === 'object' &&
    value.details !== null
  );
}

/** Turns an openapi-fetch `error` into something to throw from a query or mutation. */
export function toApiError(error: unknown, response: Response): Error {
  if (isErrorBody(error)) {
    return new ApiError(response.status, error);
  }
  // Not the envelope: a proxy or gateway answered instead of the API.
  return new Error(`Request failed with status ${String(response.status)}`);
}

export function describeError(error: Error): string {
  return error instanceof ApiError
    ? error.message
    : 'The server could not be reached. Check that the API is running and try again.';
}

/** Query retry policy: a definite answer from the API (404, 403, 422…) will not change. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && !error.retryable) {
    return false;
  }
  return failureCount < 2;
}
