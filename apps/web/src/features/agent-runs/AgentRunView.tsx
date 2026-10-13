import { RunPanel } from './RunPanel';
import { StartRun } from './StartRun';

interface AgentRunViewProps {
  projectId: string;
  /** The run to show, or null to offer starting one. */
  runId: string | null;
  onRunSelected: (runId: string | null) => void;
}

export function AgentRunView({ projectId, runId, onRunSelected }: AgentRunViewProps) {
  if (runId === null) {
    return <StartRun projectId={projectId} onRunSelected={onRunSelected} />;
  }
  return <RunPanel projectId={projectId} runId={runId} onRunSelected={onRunSelected} />;
}
