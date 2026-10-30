import { useMatch, useSearchParams } from 'react-router';

import {
  activityPath,
  BACKLOG_ROUTE,
  backlogPath,
  changesPath,
  CHAT_ROUTE,
  chatPath,
  discussionPath,
  peoplePath,
  sourcesPath,
} from '@/app/paths';
import { lastRunId, useRun } from '@/features/agent-runs';
import { useBacklogVersion, useVersionHistory } from '@/features/backlog';
import { useCurrentUser } from '@/features/identity';
import { useProject, useUnconfirmedSpeakers } from '@/features/projects';
import { useSources } from '@/features/sources';

import { backlogAttention, chatAttention, nextStep, roleLabel, statusChip } from './projectStatus';
import type { ProjectStatus } from './projectStatus';

/**
 * Reads the project's state for the shell from the same queries the pages use. The run and
 * version come from the URL; on a page that names neither, from the last run this browser
 * started, and without one, from the project's draft in progress or current baseline.
 */
export function useProjectStatus(projectId: string): ProjectStatus {
  const [searchParams] = useSearchParams();
  const { data: user } = useCurrentUser();
  const { data: sources } = useSources(projectId);
  const { data: project } = useProject(projectId);
  const scope = project?.status;
  const { data: unconfirmed } = useUnconfirmedSpeakers(projectId);

  // Only the chat and backlog pages keep a run or backlog version in their query string.
  const onChatPage = useMatch(CHAT_ROUTE) !== null;
  const onBacklogPage = useMatch(BACKLOG_ROUTE) !== null;
  const urlRunId = onChatPage || onBacklogPage ? searchParams.get('run') : null;
  const urlVersionId = onBacklogPage ? searchParams.get('version') : null;
  const runId = urlRunId ?? (urlVersionId ? null : lastRunId(projectId));
  const { data: run } = useRun(runId);
  const projectVersionId = scope ? (scope.open_version_id ?? scope.baseline_version_id) : null;
  const versionId =
    run?.candidate_version_id ?? (runId ? null : (urlVersionId ?? projectVersionId));
  const { data: version } = useBacklogVersion(projectId, versionId);
  // Only an approved version other than the baseline needs its own number from the history.
  const isPastVersion =
    version?.state === 'approved' &&
    scope?.baseline_version_id !== null &&
    scope?.baseline_version_id !== version.id;
  const { data: history } = useVersionHistory(projectId, isPastVersion);
  const versionNumber = history?.find((summary) => summary.id === version?.id)?.number ?? null;

  const startRunPath = chatPath(projectId);
  const chatInView = run ? `${startRunPath}?run=${run.id}` : startRunPath;
  const backlogInView = version
    ? `${backlogPath(projectId)}?version=${version.id}`
    : run
      ? `${backlogPath(projectId)}?run=${run.id}`
      : backlogPath(projectId);
  const role = user ? roleLabel(user.memberships, projectId) : null;

  return {
    projectId,
    roleLabel: role,
    chip: statusChip(run, version, sources?.length, scope, versionNumber),
    nextStep: nextStep({
      roleLabel: role,
      run,
      version,
      sourceCount: sources?.length,
      unconfirmedSpeakers: unconfirmed?.length,
      chatPath: chatInView,
      backlogPath: backlogInView,
      startRunPath,
      sourcesPath: sourcesPath(projectId),
    }),
    chatAttention: chatAttention(run),
    backlogAttention: backlogAttention(version),
    peopleAttention: unconfirmed?.length ?? 0,
    chatPath: chatInView,
    backlogPath: backlogInView,
    changesPath: changesPath(projectId),
    discussionPath: discussionPath(projectId),
    sourcesPath: sourcesPath(projectId),
    peoplePath: peoplePath(projectId),
    runInView: onChatPage && urlRunId !== null ? (run ?? null) : null,
    activityPath: activityPath(projectId),
  };
}
