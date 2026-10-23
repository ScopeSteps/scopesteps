import { Banner } from '@/components/Banner';

import { useAgentModel } from './useAgentModel';

/**
 * Says, on every page, that the agent's answers are replayed from a recording. A replay must
 * never pass for a live agent run.
 */
export function ReplayBanner() {
  const { data: model } = useAgentModel();
  if (!model?.replay) {
    return null;
  }
  return (
    <div className="px-4 pt-3">
      <Banner tone="warn" role="status">
        <strong className="font-semibold">Replay, not a live agent.</strong> The agent&apos;s
        answers are replayed from a recorded run of {model.model_id}. They follow that recording
        only.
      </Banner>
    </div>
  );
}
