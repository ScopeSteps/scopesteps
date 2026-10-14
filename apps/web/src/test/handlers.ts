import { http, HttpResponse } from 'msw';

import {
  BRIEF,
  BRIEF_BLOCKS,
  PROJECT,
  PROJECT_ID,
  REVIEWER,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
} from '@/test/fixtures';

export const API = '*/api/v1';
export const SOURCES_URL = `${API}/projects/${PROJECT_ID}/sources`;

/**
 * A project as a page first loads it: the signed-in editor, the project with its limits, and
 * the stored brief and transcript with their paragraphs. Override any of them with `server.use`.
 */
export function projectHandlers() {
  return [
    http.get(`${API}/me`, () => HttpResponse.json(REVIEWER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () => HttpResponse.json(PROJECT)),
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] })),
    http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () => HttpResponse.json(BRIEF_BLOCKS)),
    http.get(`${SOURCES_URL}/${TRANSCRIPT.id}/blocks`, () => HttpResponse.json(TRANSCRIPT_BLOCKS)),
  ];
}
