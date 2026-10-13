import type { components } from '@scopesteps/api-client';

export type SourceVersion = components['schemas']['SourceVersionResponse'];
export type SourceBlock = components['schemas']['SourceBlockResponse'];
export type SourceKind = components['schemas']['SourceKind'];

export const KIND_LABELS: Record<SourceKind, string> = {
  brief: 'Project brief',
  transcript: 'Meeting transcript',
};
