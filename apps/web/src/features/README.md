# Features

One folder per backend module, named in kebab-case: `projects/`, `sources/`, `evidence/`,
`backlog/`, `change-control/`, `agent-runs/`. Create a folder when its first screen is built.

Each feature exposes its public components and hooks through `index.ts`. Other features and
`app/` import only from that file; ESLint enforces this.
