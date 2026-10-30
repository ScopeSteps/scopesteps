import { SideSheet } from '@/components/SideSheet';

import { DiscussionPanel } from './DiscussionPanel';

interface DiscussionSheetProps {
  projectId: string;
  item: { id: string; title: string };
  onClose: () => void;
}

/** One epic's or story's discussions beside the backlog. */
export function DiscussionSheet({ projectId, item, onClose }: DiscussionSheetProps) {
  return (
    <SideSheet title={`Discussion · ${item.title}`} onClose={onClose}>
      <DiscussionPanel
        projectId={projectId}
        scope={{ kind: 'item', itemId: item.id, title: item.title }}
      />
    </SideSheet>
  );
}
