import { describe, expect, it } from 'vitest';

import { safeReturnPath, signInPath } from './paths';

describe('safeReturnPath', () => {
  it.each([
    ['/projects/p1/backlog?run=r1#s2', '/projects/p1/backlog?run=r1#s2'],
    ['/', '/'],
    [null, '/'],
    ['', '/'],
    ['projects/p1', '/'],
    ['//evil.example/x', '/'],
    ['/\\evil.example/x', '/'],
    ['https://evil.example/x', '/'],
    ['javascript:alert(1)', '/'],
    ['/sign-in', '/'],
    ['/sign-in?next=/sign-in', '/'],
  ])('follows %j to %j', (raw, expected) => {
    expect(safeReturnPath(raw)).toBe(expected);
  });
});

describe('signInPath', () => {
  it('remembers a page to return to, and leaves out the home page', () => {
    expect(signInPath('/projects/p1/chat?run=r1')).toBe(
      '/sign-in?next=%2Fprojects%2Fp1%2Fchat%3Frun%3Dr1',
    );
    expect(signInPath('/')).toBe('/sign-in');
    expect(signInPath()).toBe('/sign-in');
  });
});
