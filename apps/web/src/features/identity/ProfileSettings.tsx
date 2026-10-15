import { useState } from 'react';
import type { SubmitEvent } from 'react';

import type { components } from '@scopesteps/api-client';

import { Avatar } from '@/components/Avatar';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { useToast } from '@/components/toastContext';
import { describeError } from '@/lib/apiError';

import { useCurrentUser } from './useCurrentUser';
import type { ProfileField } from './useUpdateProfile';
import {
  isStaleProfile,
  PROFILE_LIMITS,
  rejectedProfileField,
  useUpdateProfile,
} from './useUpdateProfile';

type CurrentUser = components['schemas']['CurrentUserResponse'];

/** The signed-in user's name, job title and about text, saved to the server only. */
export function ProfileSettings() {
  const { data: user, error, refetch } = useCurrentUser();

  if (!user) {
    return (
      <>
        <h3 className="text-[15px] font-semibold">Profile</h3>
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
            Could not load your profile. {describeError(error)}
          </Banner>
        ) : (
          <p role="status" className="text-muted">
            Loading your profile…
          </p>
        )}
      </>
    );
  }
  return <ProfileForm user={user} />;
}

interface Draft {
  display_name: string;
  job_title: string;
  about: string;
}

function draftOf(user: CurrentUser): Draft {
  return { display_name: user.display_name, job_title: user.job_title, about: user.about };
}

function ProfileForm({ user }: { user: CurrentUser }) {
  const update = useUpdateProfile();
  const { refetch, isRefetching } = useCurrentUser();
  const showToast = useToast();
  const [draft, setDraft] = useState<Draft>(() => draftOf(user));
  // The revision the user is editing. A newer one on the server means the profile changed.
  const [baseRevision, setBaseRevision] = useState(user.revision);
  const [blankName, setBlankName] = useState(false);

  const stale = isStaleProfile(update.error);
  const rejected = rejectedProfileField(update.error);
  const otherError = update.error && !stale && rejected === null ? update.error : null;

  function fieldError(field: ProfileField): string | null {
    if (field === 'display_name' && blankName) {
      return 'Enter your name.';
    }
    return rejected?.field === field ? rejected.message : null;
  }

  function change(field: ProfileField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    if (field === 'display_name') {
      setBlankName(false);
    }
    if (!stale) {
      update.reset();
    }
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (update.isPending || stale) {
      return;
    }
    if (draft.display_name.trim() === '') {
      setBlankName(true);
      return;
    }
    update.mutate(
      { ...draft, expected_revision: baseRevision },
      {
        onSuccess: (saved) => {
          setDraft(draftOf(saved));
          setBaseRevision(saved.revision);
          showToast('Profile saved.');
        },
      },
    );
  }

  async function reload() {
    const { data } = await refetch();
    if (data) {
      setDraft(draftOf(data));
      setBaseRevision(data.revision);
      update.reset();
    }
  }

  return (
    <>
      <h3 className="text-[15px] font-semibold">Profile</h3>
      <div className="flex items-center gap-3">
        <Avatar name={draft.display_name.trim() || user.display_name} size={64} />
        <span className="text-xs text-subtle">Teammates see your initials next to your name.</span>
      </div>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3.5">
        <TextField
          label="Full name"
          name="display_name"
          value={draft.display_name}
          maxLength={PROFILE_LIMITS.display_name}
          autoComplete="name"
          onChange={(value) => {
            change('display_name', value);
          }}
          error={fieldError('display_name')}
        />
        <TextField
          label="Job title"
          name="job_title"
          value={draft.job_title}
          maxLength={PROFILE_LIMITS.job_title}
          autoComplete="organization-title"
          onChange={(value) => {
            change('job_title', value);
          }}
          error={fieldError('job_title')}
        />
        <TextField
          label="About you"
          name="about"
          rows={3}
          value={draft.about}
          maxLength={PROFILE_LIMITS.about}
          onChange={(value) => {
            change('about', value);
          }}
          help={
            <>
              <span aria-live="polite">
                {draft.about.length} / {PROFILE_LIMITS.about}
              </span>{' '}
              · Helps teammates know what you work on.
            </>
          }
          error={fieldError('about')}
        />
        <div>
          <Button type="submit" variant="primary" disabled={update.isPending || stale}>
            {update.isPending ? 'Saving…' : 'Save profile'}
          </Button>
        </div>
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
          Your profile changed somewhere else while you were editing. Reload to see it, then save
          again.
        </Banner>
      )}
      {otherError && (
        <Banner tone="bad" role="alert">
          Your profile could not be saved. {describeError(otherError)}
        </Banner>
      )}
    </>
  );
}
