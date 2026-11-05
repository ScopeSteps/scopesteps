import { formatBytes } from './format';
import type { SourceLimits } from './types';

/** What the file input offers. The API decides by extension, so the extensions come first. */
export const ACCEPTED_SOURCE_FILES = [
  '.txt',
  '.md',
  '.markdown',
  '.docx',
  '.pdf',
  '.vtt',
  'text/plain',
  'text/markdown',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/pdf',
  'text/vtt',
].join(',');

const TEXT_EXTENSIONS = ['.txt', '.md', '.markdown'];
// Converted to text by the API, with their own size limit (ADR 0025).
const DOCUMENT_EXTENSIONS = ['.docx', '.pdf', '.vtt'];

/** The types the API takes, as the picker names them. */
export const ACCEPTED_TYPES_TEXT = '.txt, .md, .docx, .pdf or .vtt';

/** The types and sizes the API takes, in one line: "Text or Markdown up to 512 KB each; …". */
export function acceptedFilesSummary(limits: SourceLimits): string {
  return `Text or Markdown up to ${formatBytes(limits.max_bytes)} each; Word, PDF or .vtt up to ${formatBytes(limits.max_document_bytes)}`;
}

/**
 * A quick check before uploading, so an obvious mistake is caught without a round trip. It
 * mirrors the API's type and size rules; the API checks again, reads the file, and its answer
 * is the one shown. Returns why the file would be refused, or null.
 */
export function checkSourceFile(file: File, limits: SourceLimits | undefined): string | null {
  const name = file.name.toLowerCase();
  const isText = TEXT_EXTENSIONS.some((extension) => name.endsWith(extension));
  const isDocument = DOCUMENT_EXTENSIONS.some((extension) => name.endsWith(extension));
  if (!isText && !isDocument) {
    return `${file.name} is not a ${ACCEPTED_TYPES_TEXT} file.`;
  }
  if (file.size === 0) {
    return `${file.name} is empty.`;
  }
  const maxBytes = limits && (isText ? limits.max_bytes : limits.max_document_bytes);
  if (maxBytes !== undefined && file.size > maxBytes) {
    return `${file.name} is larger than ${formatBytes(maxBytes)}.`;
  }
  return null;
}
