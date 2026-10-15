import { describe, expect, it } from 'vitest';

import { openRightsCount, rightsSummary } from './people';
import type { Person } from './people';

type Stated = Person['extracted']['stated_rights'];
type Confirmed = NonNullable<Person['confirmed_rights']>['rights'];

function person(stated: Stated, confirmed: Confirmed | null): Person {
  return {
    id: '019a3a5e-0000-7000-8000-000000000201',
    project_id: '019a3a5e-0000-7000-8000-000000000001',
    revision: 1,
    name: 'Dana',
    role: '',
    extracted: {
      name: 'Dana',
      role: '',
      said: '',
      stated_rights: stated,
      evidence: [],
      rights_evidence: [],
      run_id: '019a3a5e-0000-7000-8000-0000000000f1',
      extracted_at: '2026-10-13T09:00:00Z',
    },
    correction: null,
    confirmed_rights: confirmed && {
      rights: confirmed,
      confirmed_by: '019a3a5e-0000-7000-8000-000000000002',
      confirmed_at: '2026-10-14T09:00:00Z',
    },
    created_at: '2026-10-13T09:00:00Z',
  };
}

describe('rightsSummary', () => {
  it.each([
    ['decides', null, 'Stated in source', 'accent'],
    ['advises', null, 'Stated in source', 'accent'],
    ['not_stated', 'decides', 'Confirmed', 'ok'],
    ['not_stated', 'advises', 'Confirmed', 'ok'],
    ['not_stated', 'unknown', 'Checked', 'neutral'],
    ['not_stated', null, 'Not stated', 'warn'],
  ] as const)('tags stated %s, confirmed %s, as "%s"', (stated, confirmed, tag, tone) => {
    expect(rightsSummary(person(stated, confirmed))).toMatchObject({ tag, tone });
  });
});

describe('openRightsCount', () => {
  it('counts only people whose rights are neither stated nor confirmed, unknown included', () => {
    const people = [
      person('decides', null),
      person('not_stated', 'unknown'),
      person('not_stated', 'advises'),
      person('not_stated', null),
      person('not_stated', null),
    ];

    expect(openRightsCount(people)).toBe(2);
    expect(openRightsCount(undefined)).toBe(0);
  });
});
