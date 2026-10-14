export default {
  extends: ['@commitlint/config-conventional'],
  // Dependabot always writes "Bump ..." in sentence case and its titles cannot be configured, so
  // its PRs failed subject-case. Only its exact title shape is exempt.
  ignores: [(message) => /^chore\(deps(-dev)?\): Bump \S+ from \S+ to \S+/.test(message)],
};
