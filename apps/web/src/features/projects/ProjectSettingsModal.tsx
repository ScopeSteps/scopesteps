import { useId, useRef, useState } from 'react';
import type { SubmitEvent } from 'react';

import type { components } from '@scopesteps/api-client';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { TextField } from '@/components/TextField';
import { useToast } from '@/components/toastContext';
import { ApiError, describeError } from '@/lib/apiError';

import { isStaleProject, rejectedName } from './projectErrors';
import { ProjectLimits } from './ProjectLimits';
import { ProjectMembers } from './ProjectMembers';
import { useProject } from './useProject';
import { useRenameProject } from './useRenameProject';

type Project = components['schemas']['ProjectDetailResponse'];

const NAME_HELP = 'Shown in the sidebar, on every version and in exports.';

interface ProjectSettingsModalProps {
  projectId: string;
  onClose: () => void;
}

/** The project's name, its limits and its members. Renaming needs the Editor or Approver role. */
export function ProjectSettingsModal({ projectId, onClose }: ProjectSettingsModalProps) {
  const { data: project, error, refetch } = useProject(projectId);

  if (!project) {
    return (
      <Modal
        title="Project settings"
        onClose={onClose}
        footer={<Button onClick={onClose}>Close</Button>}
      >
        {error ? (
          <Banner
            tone="bad"
            role="alert"
            action={
              <Button size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            }
          >
            Could not load the project. {describeError(error)}
          </Banner>
        ) : (
          <p role="status" className="text-muted">
            Loading project settings…
          </p>
        )}
      </Modal>
    );
  }

  const canRename = project.roles.includes('editor') || project.roles.includes('approver');
  return canRename ? (
    <RenameForm project={project} onClose={onClose} />
  ) : (
    <Modal
      title="Project settings"
      onClose={onClose}
      footer={
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      }
    >
      <div className="flex flex-col gap-[5px]">
        <span className="text-[13px] font-semibold">Project name</span>
        <span className="break-words">{project.name}</span>
        <span className="text-xs text-subtle">
          {NAME_HELP} You have view-only access: a Business analyst or a Product owner can rename
          it.
        </span>
      </div>
      <ProjectLimits limits={project.limits} />
      <ProjectMembers projectId={projectId} />
    </Modal>
  );
}

interface RenameFormProps {
  project: Project;
  onClose: () => void;
}

function RenameForm({ project, onClose }: RenameFormProps) {
  const rename = useRenameProject(project.id);
  const { refetch, isRefetching } = useProject(project.id);
  const showToast = useToast();
  const [name, setName] = useState(project.name);
  // The revision the user is editing. A newer one on the server means someone else renamed it.
  const [baseRevision, setBaseRevision] = useState(project.revision);
  const [blank, setBlank] = useState(false);
  const idempotencyKey = useRef<string | null>(null);
  const formId = useId();

  const stale = isStaleProject(rename.error);
  const fieldError = blank ? 'Enter a project name.' : rejectedName(rename.error);
  const otherError = rename.error && !stale && fieldError === null ? rename.error : null;

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rename.isPending) {
      return;
    }
    if (name.trim() === '') {
      setBlank(true);
      return;
    }
    idempotencyKey.current ??= crypto.randomUUID();
    rename.mutate(
      { name, expectedRevision: baseRevision, idempotencyKey: idempotencyKey.current },
      {
        onSuccess: () => {
          showToast('Project settings saved.');
          onClose();
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            idempotencyKey.current = null;
          }
        },
      },
    );
  }

  async function reload() {
    const { data } = await refetch();
    if (data) {
      setName(data.name);
      setBaseRevision(data.revision);
      rename.reset();
    }
  }

  return (
    <Modal
      title="Project settings"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            type="submit"
            form={formId}
            variant="primary"
            disabled={rename.isPending || stale}
          >
            {rename.isPending ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
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
          maxLength={project.limits.project_name_max_chars}
          focusOnMount
          onChange={(value) => {
            setName(value);
            setBlank(false);
            idempotencyKey.current = null;
            if (!stale) {
              rename.reset();
            }
          }}
          help={NAME_HELP}
          error={fieldError}
        />
      </form>
      {stale && (
        <Banner
          tone="warn"
          role="alert"
          action={
            <Button size="sm" disabled={isRefetching} onClick={() => void reload()}>
              {isRefetching ? 'Reloading…' : 'Reload'}
            </Button>
          }
        >
          Someone else changed this project while you were editing. Reload to see its current name,
          then save again.
        </Banner>
      )}
      {otherError && (
        <Banner tone="bad" role="alert">
          The project could not be renamed. {describeError(otherError)}
        </Banner>
      )}
      <ProjectLimits limits={project.limits} />
      <ProjectMembers projectId={project.id} />
    </Modal>
  );
}
