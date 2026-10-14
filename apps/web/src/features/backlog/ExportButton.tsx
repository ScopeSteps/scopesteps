import { useState } from 'react';

import { Button } from '@/components/Button';

import { ExportModal } from './ExportModal';

interface ExportButtonProps {
  projectId: string;
  /** An approved version: every member of the project may export it. */
  versionId: string;
}

export function ExportButton({ projectId, versionId }: ExportButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        Export
      </Button>
      {open && (
        <ExportModal
          projectId={projectId}
          versionId={versionId}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
