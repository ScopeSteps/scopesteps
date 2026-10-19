export default {
  extends: ['@commitlint/config-conventional'],
  // Dependabot always writes "Bump ..." in sentence case and its titles cannot be configured, so
  // its PRs failed subject-case. Only its exact title shapes are exempt: one dependency
  // ("Bump x from 1 to 2") or a group ("Bump the python group with 6 updates").
  ignores: [
    (message) =>
      /^chore\(deps(-dev)?\): Bump (\S+ from \S+ to \S+|the \S+ group( across \d+ director(y|ies))? with \d+ updates?)/.test(
        message,
      ),
  ],
};
