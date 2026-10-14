import { http, HttpResponse } from 'msw';

import {
  BRIEF,
  BRIEF_BLOCKS,
  PROJECT,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
} from '@/test/fixtures';

export const API = '*/api/v1';
export const SOURCES_URL = `${API}/projects/${PROJECT_ID}/sources`;
export const VERSIONS_URL = `${API}/projects/${PROJECT_ID}/backlogs`;

/**
 * A project as a page first loads it: the signed-in editor, the project with its limits, the
 * stored brief and transcript with their paragraphs, the reviewer as its one member, and an
 * empty version history. Override any of them with `server.use`.
 */
export function projectHandlers() {
  return [
    http.get(`${API}/me`, () => HttpResponse.json(REVIEWER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () => HttpResponse.json(PROJECT)),
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] })),
    http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () => HttpResponse.json(BRIEF_BLOCKS)),
    http.get(`${SOURCES_URL}/${TRANSCRIPT.id}/blocks`, () => HttpResponse.json(TRANSCRIPT_BLOCKS)),
    http.get(`${API}/projects/${PROJECT_ID}/members`, () =>
      HttpResponse.json({
        members: [
          {
            user_id: REVIEWER_ID,
            display_name: REVIEWER.display_name,
            job_title: '',
            roles: ['editor'],
          },
        ],
      }),
    ),
    http.get(VERSIONS_URL, () => HttpResponse.json({ versions: [], next_cursor: null })),
  ];
}
