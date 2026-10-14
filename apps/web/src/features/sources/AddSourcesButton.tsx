import { useState } from 'react';

import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';

import { AddSourcesModal } from './AddSourcesModal';

interface AddSourcesButtonProps {
  projectId: string;
  variant?: 'primary' | 'default';
  size?: 'md' | 'sm';
  /** A bare "+" with the label as its accessible name, as in the chat composer. */
  iconOnly?: boolean;
}

const LABEL = 'Add sources';

/** Opens the Add sources modal. Offer it only to someone who may upload. */
export function AddSourcesButton({
  projectId,
  variant = 'primary',
  size = 'md',
  iconOnly = false,
}: AddSourcesButtonProps) {
  const [open, setOpen] = useState(false);
  const openModal = () => {
    setOpen(true);
  };

  return (
    <>
      {iconOnly ? (
        <IconButton icon="plus" label={LABEL} onClick={openModal} />
      ) : (
        <Button variant={variant} size={size} onClick={openModal}>
          {size === 'md' && <Icon name="upload" size={16} />}
          {LABEL}
        </Button>
      )}
      {open && (
        <AddSourcesModal
          projectId={projectId}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
