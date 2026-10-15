import type { components } from '@scopesteps/api-client';

export type SourceVersion = components['schemas']['SourceVersionResponse'];
export type SourceBlock = components['schemas']['SourceBlockResponse'];
export type SourceKind = components['schemas']['SourceKind'];
export type SourceLimits = components['schemas']['SourceLimitsResponse'];
export type RemovedSource = components['schemas']['RemovedSourceResponse'];

export const SOURCE_KINDS: readonly SourceKind[] = ['brief', 'transcript', 'supporting_document'];

export const KIND_LABELS: Record<SourceKind, string> = {
  brief: 'Project brief',
  transcript: 'Meeting transcript',
  supporting_document: 'Supporting document',
  change_request: 'Change request',
};

/** The kind in one word, for citation chips where space is short. */
export const KIND_SHORT_LABELS: Record<SourceKind, string> = {
  brief: 'Brief',
  transcript: 'Transcript',
  supporting_document: 'Document',
  change_request: 'Request',
};

/** A file chosen in the browser and the kind it is stored as. */
export interface SourceFile {
  kind: SourceKind;
  file: File;
}

/** The stable label the API's source number gives a source, "SRC-3". */
export function sourceLabel(sourceNumber: number): string {
  return `SRC-${String(sourceNumber)}`;
}
