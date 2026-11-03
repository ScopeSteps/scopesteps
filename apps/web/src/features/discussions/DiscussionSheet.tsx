import { SideSheet } from '@/components/SideSheet';

import { DiscussionPanel } from './DiscussionPanel';
import type { DiscussionLinks } from './DiscussionPanel';

interface DiscussionSheetProps {
  projectId: string;
  item: { id: string; title: string };
  onClose: () => void;
  links?: DiscussionLinks;
}

/** One epic's or story's discussions beside the backlog. */
export function DiscussionSheet({ projectId, item, onClose, links }: DiscussionSheetProps) {
  return (
    <SideSheet title={`Discussion · ${item.title}`} onClose={onClose}>
      <DiscussionPanel
        projectId={projectId}
        scope={{ kind: 'item', itemId: item.id, title: item.title }}
        {...(links ? { links } : {})}
      />
    </SideSheet>
  );
}
