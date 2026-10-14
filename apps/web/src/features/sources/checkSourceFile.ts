import { formatBytes } from './format';
import type { SourceLimits } from './types';

/** What the file input offers. The API decides by extension, so the extensions come first. */
export const ACCEPTED_SOURCE_FILES = '.txt,.md,.markdown,text/plain,text/markdown';

const ACCEPTED_EXTENSIONS = ['.txt', '.md', '.markdown'];

/**
 * A quick check before uploading, so an obvious mistake is caught without a round trip. It
 * mirrors the API's type and size rules; the API checks again, and its answer is the one shown.
 * Returns why the file would be refused, or null.
 */
export function checkSourceFile(file: File, limits: SourceLimits | undefined): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return `${file.name} is not a .txt or .md file.`;
  }
  if (file.size === 0) {
    return `${file.name} is empty.`;
  }
  if (limits && file.size > limits.max_bytes) {
    return `${file.name} is larger than ${formatBytes(limits.max_bytes)}.`;
  }
  return null;
}
