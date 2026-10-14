import { useMatch, useSearchParams } from 'react-router';

import { BACKLOG_ROUTE, backlogPath, CHAT_ROUTE, chatPath, sourcesPath } from '@/app/paths';
import { lastRunId, useRun } from '@/features/agent-runs';
import { useBacklogVersion } from '@/features/backlog';
import { useCurrentUser } from '@/features/identity';
import { useSources } from '@/features/sources';

import { backlogAttention, chatAttention, nextStep, roleLabel, statusChip } from './projectStatus';
import type { ProjectStatus } from './projectStatus';

/**
 * Reads the project's state for the shell from the same queries the pages use. The run and
 * version come from the URL; on a page that names neither, from the last run this browser
 * started, because the API cannot yet list a project's runs or versions.
 */
export function useProjectStatus(projectId: string): ProjectStatus {
  const [searchParams] = useSearchParams();
  const { data: user } = useCurrentUser();
  const { data: sources } = useSources(projectId);

  // Only the chat and backlog pages keep a run or backlog version in their query string.
  const onChatPage = useMatch(CHAT_ROUTE) !== null;
  const onBacklogPage = useMatch(BACKLOG_ROUTE) !== null;
  const urlRunId = onChatPage || onBacklogPage ? searchParams.get('run') : null;
  const urlVersionId = onBacklogPage ? searchParams.get('version') : null;
  const runId = urlRunId ?? (urlVersionId ? null : lastRunId(projectId));
  const { data: run } = useRun(runId);
  const versionId = run?.candidate_version_id ?? (runId ? null : urlVersionId);
  const { data: version } = useBacklogVersion(projectId, versionId);

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
    chip: statusChip(run, version, sources?.length),
    nextStep: nextStep({
      roleLabel: role,
      run,
      version,
      sourceCount: sources?.length,
      chatPath: chatInView,
      backlogPath: backlogInView,
      startRunPath,
      sourcesPath: sourcesPath(projectId),
    }),
    chatAttention: chatAttention(run),
    backlogAttention: backlogAttention(version),
    chatPath: chatInView,
    backlogPath: backlogInView,
    sourcesPath: sourcesPath(projectId),
    runInView: onChatPage && urlRunId !== null ? (run ?? null) : null,
  };
}
