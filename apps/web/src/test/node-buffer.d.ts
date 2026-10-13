/** Node's own File class, typed as the browser's. Only test-setup.ts needs it. */
declare module 'node:buffer' {
  export const File: typeof globalThis.File;
}
