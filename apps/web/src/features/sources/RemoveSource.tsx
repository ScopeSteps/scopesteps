import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/Button';
import { useToast } from '@/components/toastContext';
import { describeError } from '@/lib/apiError';

import { describeSourceUsage } from './sourceUsage';
import { sourceLabel } from './types';
import type { SourceVersion } from './types';
import { useRemoveSource } from './useRemoveSource';

interface RemoveSourceProps {
  projectId: string;
  version: SourceVersion;
  onRemoved: () => void;
}

/**
 * The source viewer's footer for an editor: removes the source after a confirmation, or says
 * why the API keeps it. Whether anything refers to a source is known only to the API, so the
 * reason appears once it has refused.
 */
export function RemoveSource({ projectId, version, onRemoved }: RemoveSourceProps) {
  const remove = useRemoveSource(projectId);
  const showToast = useToast();
  const [confirming, setConfirming] = useState(false);
  const label = sourceLabel(version.source_number);
  const usage = describeSourceUsage(remove.error);
  const removeButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const focusAfterToggle = useRef(false);

  // The button pressed is replaced by the next step's, so focus follows it there.
  useEffect(() => {
    if (focusAfterToggle.current) {
      focusAfterToggle.current = false;
      (confirming ? confirmButton : removeButton).current?.focus();
    }
  }, [confirming]);

  if (usage !== null) {
    return (
      <p role="alert" className="mr-auto self-center text-[13px] text-muted">
        Used as evidence, so it can’t be removed{usage ? `: cited by ${usage}` : ''}.
      </p>
    );
  }

  if (!confirming) {
    return (
      <Button
        ref={removeButton}
        variant="danger"
        onClick={() => {
          setConfirming(true);
          focusAfterToggle.current = true;
        }}
      >
        Remove source
      </Button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-2.5">
      {remove.error ? (
        <p role="alert" className="text-[13px] text-bad-ink">
          Could not remove {label}. {describeError(remove.error)}
        </p>
      ) : (
        <p className="text-[13px]">
          Remove {label} from the project? The agent stops using it from the next run.
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          onClick={() => {
            setConfirming(false);
            focusAfterToggle.current = true;
            remove.reset();
          }}
        >
          Cancel
        </Button>
        <Button
          ref={confirmButton}
          variant="danger"
          disabled={remove.isPending}
          onClick={() => {
            remove.mutate(version.source_id, {
              onSuccess: () => {
                showToast(`${label} removed.`);
                onRemoved();
              },
            });
          }}
        >
          {remove.isPending ? 'Removing…' : `Remove ${label}`}
        </Button>
      </div>
    </div>
  );
}
