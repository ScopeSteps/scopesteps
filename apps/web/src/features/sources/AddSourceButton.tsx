import { useState } from 'react';

import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/IconButton';

import { AddSourceModal } from './AddSourceModal';

interface AddSourceButtonProps {
  projectId: string;
  variant?: 'primary' | 'default';
  size?: 'md' | 'sm';
  /** The visible text, or the accessible name of the bare "+". */
  label?: string;
  /** A bare "+" with the label as its accessible name, as in the chat composer. */
  iconOnly?: boolean;
}

/** Opens the Add a source modal. Offer it only to someone who may upload. */
export function AddSourceButton({
  projectId,
  variant = 'primary',
  size = 'md',
  label = 'Add source',
  iconOnly = false,
}: AddSourceButtonProps) {
  const [open, setOpen] = useState(false);
  const openModal = () => {
    setOpen(true);
  };

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
        />
      )}
    </>
  );
}
