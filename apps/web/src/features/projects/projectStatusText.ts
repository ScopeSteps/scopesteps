import type { components } from '@scopesteps/api-client';

type ScopeStatus = components['schemas']['ScopeStatusResponse'];

/** Where the project's scope stands, in the words of the sidebar's project card. */
export function projectStatusText(status: ScopeStatus): string {
  switch (status.state) {
    case 'no_baseline':
      return 'No baseline yet';
    case 'draft_in_progress':
      return 'Draft in progress';
    case 'candidate_in_review':
      return status.baseline_version === null
        ? 'Candidate in review'
        : `Candidate v${String(status.baseline_version + 1)} in review`;
    case 'baseline':
      return status.baseline_version === null
        ? 'Baseline approved'
        : `Baseline v${String(status.baseline_version)} approved`;
  }
}
