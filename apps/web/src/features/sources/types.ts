import type { components } from '@scopesteps/api-client';

export type SourceVersion = components['schemas']['SourceVersionResponse'];
export type SourceBlock = components['schemas']['SourceBlockResponse'];
export type SourceKind = components['schemas']['SourceKind'];
export type MediaType = components['schemas']['MediaType'];
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

/**
 * A file chosen in the browser and the kind it is stored as. The kind is null until the person
 * picks it: the app never guesses one, because people choose files in any order.
 */
export interface SourceFile {
  kind: SourceKind | null;
  file: File;
}

/** A chosen file whose kind has been picked, so it can be uploaded. */
export interface TypedSourceFile extends SourceFile {
  kind: SourceKind;
}

/** Whether every file has a kind, so the files can be uploaded. */
export function everyKindChosen(files: readonly SourceFile[]): files is readonly TypedSourceFile[] {
  return files.every((entry) => entry.kind !== null);
}

/** The stable label the API's source number gives a source, "SRC-3". */
export function sourceLabel(sourceNumber: number): string {
  return `SRC-${String(sourceNumber)}`;
}
