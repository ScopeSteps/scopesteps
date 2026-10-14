import { ApiError } from '@/lib/apiError';

import { plural } from './format';

const USAGE_NOUNS: Record<string, [string, string]> = {
  run: ['agent run', 'agent runs'],
  backlog_version: ['backlog version', 'backlog versions'],
  person: ['person', 'people'],
};

function isCountMap(value: unknown): value is Record<string, number> {
  return (
    typeof value === 'object' &&
    value !== null &&
    Object.values(value).every((count) => typeof count === 'number')
  );
}

function joinList(parts: readonly string[]): string {
  if (parts.length < 2) {
    return parts.join('');
  }
  return `${parts.slice(0, -1).join(', ')} and ${parts.slice(-1).join('')}`;
}

/**
 * Why the API refused to remove a source, from the counts in `details.used_by` of a
 * `SOURCE_IN_USE` refusal: "1 agent run and 2 people". Null for any other error.
 */
export function describeSourceUsage(error: Error | null): string | null {
  if (!(error instanceof ApiError) || error.code !== 'SOURCE_IN_USE') {
    return null;
  }
  const usedBy = error.details.used_by;
  if (!isCountMap(usedBy)) {
    return '';
  }
  return joinList(
    Object.entries(usedBy)
      .filter(([, count]) => count > 0)
      .map(([kind, count]) => {
        const [one, many] = USAGE_NOUNS[kind] ?? [
          kind.replaceAll('_', ' '),
          kind.replaceAll('_', ' '),
        ];
        return plural(count, one, many);
      }),
  );
}
