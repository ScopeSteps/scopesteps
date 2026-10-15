import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { PROJECT_ID, REVIEWER, REVIEWER_ID } from '@/test/fixtures';
import { server } from '@/test/server';

import { useReviewerName } from './useReviewerName';

const OTHER_ID = '019a3a5e-0000-7000-8000-000000000099';
const FORMER_ID = '019a3a5e-0000-7000-8000-000000000098';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useReviewerName', () => {
  it('names other members by their display name, never as another reviewer', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
      http.get(`*/api/v1/projects/${PROJECT_ID}/members`, () =>
        HttpResponse.json({
          members: [
            { user_id: REVIEWER_ID, display_name: 'Local Reviewer', job_title: '', roles: [] },
            { user_id: OTHER_ID, display_name: 'Priya Shah', job_title: '', roles: ['editor'] },
          ],
        }),
      ),
    );
    const { result } = renderHook(() => useReviewerName(PROJECT_ID), { wrapper });

    expect(result.current(OTHER_ID)).toBe('a reviewer');
    await waitFor(() => {
      expect(result.current(OTHER_ID)).toBe('Priya Shah');
    });
    expect(result.current(REVIEWER_ID)).toBe('Local Reviewer');
    expect(result.current(FORMER_ID)).toBe('a former member');
    expect(result.current(null)).toBe('an unknown reviewer');
  });
});
