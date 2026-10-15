import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { Tag } from '@/components/Tag';
import { TextField } from '@/components/TextField';
import { AddSourcesButton, plural, useSources } from '@/features/sources';
import { ApiError, describeError } from '@/lib/apiError';

import { rejectedName } from './projectErrors';
import { useCreateProject } from './useCreateProject';

interface NewProjectModalProps {
  onClose: () => void;
  /** The project exists; called when the user leaves the modal after creating it. */
  onDone: (projectId: string) => void;
}

interface CreatedProject {
  id: string;
  name: string;
}

function StepTags({ step }: { step: 1 | 2 }) {
  return (
    <p className="flex gap-1.5" aria-label={`Step ${String(step)} of 2`}>
      <Tag tone={step === 1 ? 'accent' : 'ok'}>1 · Name</Tag>
      <Tag tone={step === 2 ? 'accent' : 'neutral'}>2 · Sources</Tag>
    </p>
  );
}

/**
 * Names a new project, then offers to add its sources. The project is created when the name is
 * accepted, because sources are stored in a project; adding them is optional.
 */
export function NewProjectModal({ onClose, onDone }: NewProjectModalProps) {
  const create = useCreateProject();
  const [created, setCreated] = useState<CreatedProject | null>(null);
  const [name, setName] = useState('');
  const [blank, setBlank] = useState(false);
  // Kept across a retry whose outcome is unknown, so it cannot create a second project.
  const idempotencyKey = useRef<string | null>(null);
  const formId = useId();

  const nameRejection = rejectedName(create.error);
  const fieldError = blank ? 'Enter a project name.' : nameRejection;

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (create.isPending) {
      return;
    }
    if (name.trim() === '') {
      setBlank(true);
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    create.mutate(
      { name, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: (project) => {
          setCreated({ id: project.id, name: project.name });
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            idempotencyKey.current = null;
          }
        },
      },
    );
  }

  if (created) {
    // The project exists from here on, so leaving the modal in any way opens it.
    const finish = () => {
      onDone(created.id);
    };
    return (
      <Modal
        title="New project"
        onClose={finish}
        footer={
          // Replaces the button that had focus, so focus moves on to the next action.
          <Button key="open" autoFocus variant="primary" onClick={finish}>
            Open project
          </Button>
        }
      >
        <StepTags step={2} />
        <AddSourcesStep project={created} />
      </Modal>
    );
  }

  return (
    <Modal
      title="New project"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" form={formId} variant="primary" disabled={create.isPending}>
            {create.isPending ? 'Creating…' : 'Continue'}
          </Button>
        </>
      }
    >
      <StepTags step={1} />
      <form
        id={formId}
        onSubmit={submit}
        noValidate
        autoComplete="off"
        className="flex flex-col gap-3.5"
      >
        <TextField
          label="Project name"
          value={name}
          onChange={(value) => {
            setName(value);
            setBlank(false);
            idempotencyKey.current = null;
            create.reset();
          }}
          help="You can change it later in Project settings."
          error={fieldError}
        />
      </form>
      {create.error && !nameRejection && (
        <Banner tone="bad" role="alert">
          The project could not be created. {describeError(create.error)}
        </Banner>
      )}
    </Modal>
  );
}

function AddSourcesStep({ project }: { project: CreatedProject }) {
  const { data: sources, error, isPending, refetch } = useSources(project.id);

  return (
    <>
      <p role="status" className="text-muted">
        Created <strong className="text-fg">{project.name}</strong>. Add the project brief and a
        meeting transcript now, or later from the chat or the Sources page. The agent works only
        from these files and your answers.
      </p>
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-line-strong p-[18px]">
        {isPending && <p className="text-[13px] text-subtle">Loading sources…</p>}
        {error && (
          <Banner
            tone="bad"
            role="alert"
            action={
              <Button size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            }
          >
            Could not load the project’s sources. {describeError(error)}
          </Banner>
        )}
        {sources?.length === 0 && (
          <p className="text-[13px] text-subtle">
            No sources yet. A project can start without any.
          </p>
        )}
        {sources && sources.length > 0 && (
          <>
            <ul className="m-0 flex w-full list-none flex-col gap-1.5 p-0">
              {sources.map((source) => (
                <li
                  key={source.id}
                  className="flex items-center gap-2.5 rounded-lg border border-line bg-surface px-3 py-2"
                >
                  <Icon name="sources" size={16} />
                  <span className="min-w-0 flex-1 break-words">
                    {source.filename}{' '}
                    <span className="text-xs text-subtle">
                      · {source.word_count.toLocaleString()} words
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <span className="text-xs text-subtle">{plural(sources.length, 'source')} added</span>
          </>
        )}
        <AddSourcesButton
          projectId={project.id}
          size="sm"
          variant={sources && sources.length > 0 ? 'default' : 'primary'}
        />
      </div>
    </>
  );
}
