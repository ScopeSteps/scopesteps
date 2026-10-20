import { useId, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { useCanEdit } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import type { Person } from './people';
import { SpeakerRow } from './SpeakerRow';
import { answersFrom, draftsFrom, isStaleSpeakers, refusedField } from './speakers';
import type { SpeakerAnswer, SpeakerDraft, TranscriptSpeakers } from './speakers';
import { useAssignSpeakers } from './useAssignSpeakers';
import { usePeople } from './usePeople';
import { useSpeakers } from './useSpeakers';

interface WhosWhoModalProps {
  projectId: string;
  sourceId: string;
  /** How the page names the transcript, e.g. "SRC-2 kickoff.txt". */
  sourceName: string;
  onClose: () => void;
}

/**
 * Who each speaker in a transcript is and their meeting role, as an editor confirms them
 * (ADR 0012). Nothing is filled in by a model. Saving closes it; cancelling leaves speakers
 * unconfirmed, and a run cannot start until nobody is (ADR 0015). A member without the Editor
 * role sees the answers read-only.
 */
export function WhosWhoModal({ projectId, sourceId, sourceName, onClose }: WhosWhoModalProps) {
  const speakers = useSpeakers(projectId);
  const people = usePeople(projectId);
  const canEdit = useCanEdit(projectId);
  const assign = useAssignSpeakers(projectId, sourceId);
  // Bumped when a 409 reloaded the answers, so the form starts again from them.
  const [reloads, setReloads] = useState(0);
  const formId = useId();
  // Which speaker each sent answer was for, so a refused field shows next to its speaker.
  const [sentKeys, setSentKeys] = useState<string[]>([]);
  const transcript = speakers.data?.find((each) => each.source_id === sourceId);
  const stale = isStaleSpeakers(assign.error) ? assign.error : null;
  const refused = refusedField(assign.error, sentKeys);
  const ready = transcript !== undefined && people.data !== undefined;

  function save(answers: SpeakerAnswer[], keys: string[], revision: number) {
    setSentKeys(keys);
    assign.save(answers, revision, {
      onSaved: onClose,
      onFailed: (failure) => {
        if (isStaleSpeakers(failure)) {
          setReloads((count) => count + 1);
        }
      },
    });
  }

  let body;
  if (speakers.isPending || people.isPending) {
    body = (
      <p role="status" className="text-subtle">
        Loading the speakers…
      </p>
    );
  } else if (speakers.error ?? people.error) {
    const error = speakers.error ?? people.error;
    body = (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button
            size="sm"
            onClick={() => {
              void speakers.refetch();
              void people.refetch();
            }}
          >
            Try again
          </Button>
        }
      >
        Could not load the speakers. {error ? describeError(error) : null}
      </Banner>
    );
  } else if (!ready || transcript.speakers.length === 0) {
    body = (
      <p className="text-muted">
        No speaker labels were found in this transcript, so there is no one to confirm.
      </p>
    );
  } else {
    body = (
      <>
        <p className="text-[13px] text-muted">
          Say who each speaker is and what they do in the project&apos;s meetings. The agent works
          from what you confirm, so the run starts once everyone is identified. Leave a meeting role
          blank if you don&apos;t know it.
        </p>
        {stale && (
          <Banner tone="warn" role="alert">
            Someone else changed who&apos;s who in this transcript, so your answers were not saved.
            The latest answers are shown below; check them and save again.
          </Banner>
        )}
        {assign.error && !stale && !refused && (
          <Banner tone="bad" role="alert">
            Your answers were not saved. {describeError(assign.error)}
          </Banner>
        )}
        <WhosWhoForm
          // Starts again from the server whenever its answers change there, or after a 409 reload.
          key={`${String(transcript.revision)}-${String(reloads)}`}
          formId={formId}
          transcript={transcript}
          people={people.data}
          canEdit={canEdit}
          saving={assign.isPending}
          refused={refused}
          onEdit={() => {
            if (!stale) {
              assign.reset();
            }
          }}
          onSave={save}
        />
      </>
    );
  }

  const editable = canEdit && ready && transcript.speakers.length > 0;
  return (
    <Modal
      title={`Who's who in ${sourceName}`}
      onClose={onClose}
      footer={
        editable ? (
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button type="submit" form={formId} variant="primary" disabled={assign.isPending}>
              {assign.isPending ? 'Saving…' : 'Save'}
            </Button>
          </>
        ) : (
          <Button onClick={onClose}>Done</Button>
        )
      }
    >
      {body}
    </Modal>
  );
}

interface WhosWhoFormProps {
  formId: string;
  transcript: TranscriptSpeakers;
  people: readonly Person[];
  canEdit: boolean;
  saving: boolean;
  refused: ReturnType<typeof refusedField>;
  onEdit: () => void;
  onSave: (answers: SpeakerAnswer[], keys: string[], revision: number) => void;
}

function WhosWhoForm({
  formId,
  transcript,
  people,
  canEdit,
  saving,
  refused,
  onEdit,
  onSave,
}: WhosWhoFormProps) {
  const [drafts, setDrafts] = useState<SpeakerDraft[]>(() => draftsFrom(transcript, people));

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const { answers, keys } = answersFrom(drafts, people);
    onSave(answers, keys, transcript.revision);
  }

  return (
    <form id={formId} onSubmit={submit} noValidate autoComplete="off">
      <ul aria-label="Speakers" className="m-0 list-none p-0">
        {transcript.speakers.map((speaker, index) => {
          const draft = drafts[index];
          if (!draft) {
            return null;
          }
          return (
            <SpeakerRow
              key={speaker.key}
              speaker={speaker}
              draft={draft}
              people={people}
              disabled={saving}
              refused={refused?.key === speaker.key ? refused : null}
              onChange={
                canEdit
                  ? (changed) => {
                      onEdit();
                      setDrafts((current) =>
                        current.map((each) => (each.key === changed.key ? changed : each)),
                      );
                    }
                  : null
              }
            />
          );
        })}
      </ul>
    </form>
  );
}
