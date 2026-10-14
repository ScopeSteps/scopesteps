import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { Modal } from '@/components/Modal';

interface EditedDraftWarningProps {
  revision: number;
  draftHref: string;
  onStart: () => void;
  onClose: () => void;
}

/**
 * Asked before a run starts while the draft in progress holds people's edits: a run writes a
 * new draft and does not carry those edits over, so they must never disappear unannounced.
 */
export function EditedDraftWarning({
  revision,
  draftHref,
  onStart,
  onClose,
}: EditedDraftWarningProps) {
  const draft = `draft r${String(revision)}`;
  return (
    <Modal
      title="Start a new run?"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => {
              onStart();
            }}
          >
            Start a new run anyway
          </Button>
        </>
      }
    >
      <p>
        The current {draft} has edits and answers that are not in any approved version. A new run
        writes a new draft from the sources and does not carry them over, and {draft} is no longer
        the draft in progress.
      </p>
      <div>
        <ButtonLink size="sm" to={draftHref}>
          Review {draft} instead
        </ButtonLink>
      </div>
    </Modal>
  );
}
