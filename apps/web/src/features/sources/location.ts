import type { MediaType, SourceBlock } from './types';

/** The file format in a word, as people call it. */
export const FORMAT_LABELS: Record<MediaType, string> = {
  'text/plain': 'Text',
  'text/markdown': 'Markdown',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
  'application/pdf': 'PDF',
  'text/vtt': 'WebVTT',
};

/** A time into a meeting as a transcript writes it: 872120 ms is "00:14:32". */
export function formatMeetingTime(milliseconds: number): string {
  const total = Math.floor(milliseconds / 1000);
  const parts = [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60];
  return parts.map((part) => String(part).padStart(2, '0')).join(':');
}

/** Where a paragraph is in its file, when the file says: "page 4" or "00:14:32". */
export function blockLocation(block: Pick<SourceBlock, 'page' | 'start_ms'>): string | null {
  if (block.page !== null) {
    return `page ${String(block.page)}`;
  }
  if (block.start_ms !== null) {
    return formatMeetingTime(block.start_ms);
  }
  return null;
}
