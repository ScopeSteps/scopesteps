import type { components } from '@scopesteps/api-client';

export type SourceVersion = components['schemas']['SourceVersionResponse'];
export type SourceBlock = components['schemas']['SourceBlockResponse'];
export type SourceKind = components['schemas']['SourceKind'];
export type SourceLimits = components['schemas']['SourceLimitsResponse'];

export const KIND_LABELS: Record<SourceKind, string> = {
  brief: 'Project brief',
  transcript: 'Meeting transcript',
};

/** The kind in one word, for citation chips where space is short. */
export const KIND_SHORT_LABELS: Record<SourceKind, string> = {
  brief: 'Brief',
  transcript: 'Transcript',
};
