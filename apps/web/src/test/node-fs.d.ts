/** The two Node functions a test needs to read a project file. Only index.test.ts uses them. */
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string;
}
declare module 'node:url' {
  export function fileURLToPath(url: string): string;
}
