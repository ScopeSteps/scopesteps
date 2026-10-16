import { useCallback, useState } from 'react';

import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';
import { WhosWhoAfterUpload } from '@/features/projects';

import { AddSourceModal } from './AddSourceModal';
import { sourceLabel } from './types';

interface AddSourceButtonProps {
  projectId: string;
  variant?: 'primary' | 'default';
  size?: 'md' | 'sm';
  /** The visible text, or the accessible name of the bare "+". */
  label?: string;
  /** A bare "+" with the label as its accessible name, as in the chat composer. */
  iconOnly?: boolean;
}

/**
 * Opens the Add a source modal. Offer it only to someone who may upload. When the upload adds a
 * transcript in which speakers were found, Who's who opens next.
 */
export function AddSourceButton({
  projectId,
  variant = 'primary',
  size = 'md',
  label = 'Add source',
  iconOnly = false,
}: AddSourceButtonProps) {
  const [open, setOpen] = useState(false);
  const [transcripts, setTranscripts] = useState<{ sourceId: string; sourceName: string }[]>([]);
  const openModal = () => {
    setOpen(true);
  };
  const clearTranscripts = useCallback(() => {
    setTranscripts([]);
  }, []);

  return (
    <>
      {iconOnly ? (
        <IconButton icon="plus" label={label} onClick={openModal} />
      ) : (
        <Button variant={variant} size={size} onClick={openModal}>
          {size === 'md' && <Icon name="upload" size={16} />}
          {label}
        </Button>
      )}
      {open && (
        <AddSourceModal
          projectId={projectId}
          onClose={() => {
            setOpen(false);
          }}
          onAdded={(added) => {
            setTranscripts(
              added
                .filter((version) => version.kind === 'transcript')
                .map((version) => ({
                  sourceId: version.source_id,
                  sourceName: `${sourceLabel(version.source_number)} ${version.filename}`,
                })),
            );
          }}
        />
      )}
      {transcripts.length > 0 && (
        <WhosWhoAfterUpload
          projectId={projectId}
          transcripts={transcripts}
          onDone={clearTranscripts}
        />
      )}
    </>
  );
}
