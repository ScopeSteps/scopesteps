import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { Avatar } from '@/components/Avatar';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { ApiError, describeError } from '@/lib/apiError';
import { cx } from '@/lib/cx';
import { formatRelative, formatWhen } from '@/lib/formatWhen';

import { CommentBody } from './CommentBody';
import { editableText, encodeMentions } from './mentions';
import type { MentionText } from './mentions';
import { MentionInput } from './MentionInput';
import type { Comment } from './types';
import { discussionsKey, useDiscussionCommands } from './useDiscussions';

interface CommentItemProps {
  projectId: string;
  comment: Comment;
  /** The person reading, who may change their own comment. */
  userId: string | null;
  /** "about v2", "about the draft": the backlog the comment was written against. */
  versionLabel: string | null;
  /** Moves focus here once it renders, e.g. the comment just posted. */
  focusOnMount?: boolean;
  /** The comment a notification opened: marked for a few seconds, then like any other. */
  highlighted?: boolean;
}

const HIGHLIGHT_MS = 4000;

export function CommentItem({
  projectId,
  comment,
  userId,
  versionLabel,
  focusOnMount = false,
  highlighted = false,
}: CommentItemProps) {
  const article = useRef<HTMLElement>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { run, isPending } = useDiscussionCommands(projectId);
  const queryClient = useQueryClient();
  const [marked, setMarked] = useState(highlighted);
  const mine = comment.author_id === userId;

  useEffect(() => {
    if (focusOnMount) {
      article.current?.focus();
    }
  }, [focusOnMount]);

  useEffect(() => {
    if (!highlighted) {
      return;
    }
    // jsdom has no layout, so it has no scrollIntoView either.
    if (typeof article.current?.scrollIntoView === 'function') {
      article.current.scrollIntoView({ block: 'center' });
    }
    const timer = window.setTimeout(() => {
      setMarked(false);
    }, HIGHLIGHT_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [highlighted]);

  if (comment.deleted) {
    return (
      <article className="rounded-lg border border-dashed border-line px-3 py-2 text-sm text-subtle">
        Comment deleted
      </article>
    );
  }

  const stale = error instanceof ApiError && error.status === 409;

  function act(command: Parameters<typeof run>[0], after?: () => void) {
    setError(null);
    run(command).then(after, (failure: unknown) => {
      setError(failure instanceof Error ? failure : new Error(String(failure)));
    });
  }

  return (
    <article
      ref={article}
      tabIndex={-1}
      aria-label={`${comment.author_name}, ${formatWhen(comment.created_at)}`}
      aria-current={marked ? 'true' : undefined}
      className={cx(
        'flex gap-2.5 rounded-lg transition-colors focus:shadow-focus focus:outline-none',
        marked && 'bg-accent-soft p-1.5',
      )}
    >
      <Avatar name={comment.author_name} size={26} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-subtle">
          <span className="text-[13px] font-semibold text-fg">{comment.author_name}</span>
          <time dateTime={comment.created_at} title={formatWhen(comment.created_at)}>
            {formatRelative(comment.created_at)}
          </time>
          {comment.edited_at && (
            <span title={`Edited ${formatWhen(comment.edited_at)}`}>edited</span>
          )}
          {versionLabel && <span>{versionLabel}</span>}
        </div>
        {editing ? (
          <EditForm
            projectId={projectId}
            initial={editableText(comment)}
            saving={isPending}
            onCancel={() => {
              setEditing(false);
              setError(null);
            }}
            onSave={(body) => {
              act(
                {
                  type: 'edit',
                  commentId: comment.id,
                  body,
                  expectedRevision: comment.revision,
                },
                () => {
                  setEditing(false);
                },
              );
            }}
          />
        ) : (
          <CommentBody comment={comment} userId={userId} />
        )}
        {error && (
          <Banner
            tone="bad"
            role="alert"
            action={
              stale ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setError(null);
                    setEditing(false);
                    void queryClient.invalidateQueries({ queryKey: discussionsKey(projectId) });
                  }}
                >
                  Reload
                </Button>
              ) : undefined
            }
          >
            {stale
              ? 'Someone changed this discussion since you opened it. Reload to see it as it is now.'
              : describeError(error)}
          </Banner>
        )}
        {mine && !editing && (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(true);
              }}
            >
              Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setConfirming(true);
              }}
            >
              Delete
            </Button>
          </div>
        )}
      </div>
      {confirming && (
        <Modal
          title="Delete this comment?"
          onClose={() => {
            setConfirming(false);
          }}
          footer={
            <>
              <Button
                onClick={() => {
                  setConfirming(false);
                }}
              >
                Keep it
              </Button>
              <Button
                variant="danger"
                disabled={isPending}
                onClick={() => {
                  act({ type: 'delete', commentId: comment.id }, () => {
                    setConfirming(false);
                  });
                }}
              >
                Delete comment
              </Button>
            </>
          }
        >
          <p>Its text is removed for everyone. If others replied, they see “Comment deleted”.</p>
        </Modal>
      )}
    </article>
  );
}

interface EditFormProps {
  projectId: string;
  initial: MentionText;
  saving: boolean;
  onSave: (body: string) => void;
  onCancel: () => void;
}

function EditForm({ projectId, initial, saving, onSave, onCancel }: EditFormProps) {
  const [value, setValue] = useState(initial);
  return (
    <div className="flex flex-col gap-2">
      <MentionInput
        projectId={projectId}
        label="Edit comment"
        value={value}
        autoFocus
        onChange={setValue}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            onSave(encodeMentions(value));
          }
        }}
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="primary"
          disabled={saving || value.text.trim() === ''}
          onClick={() => {
            onSave(encodeMentions(value));
          }}
        >
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}
