import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { Avatar } from '@/components/Avatar';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { ApiError, describeError } from '@/lib/apiError';
import { formatRelative, formatWhen } from '@/lib/formatWhen';

import { CommentBody } from './CommentBody';
import type { Comment } from './types';
import { discussionsKey, useDiscussionCommands } from './useDiscussions';

interface CommentItemProps {
  projectId: string;
  comment: Comment;
  mine: boolean;
  /** "about v2", "about the draft": the backlog the comment was written against. */
  versionLabel: string | null;
  /** Moves focus here once it renders, e.g. the comment just posted. */
  focusOnMount?: boolean;
}

export function CommentItem({
  projectId,
  comment,
  mine,
  versionLabel,
  focusOnMount = false,
}: CommentItemProps) {
  const article = useRef<HTMLElement>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { run, isPending } = useDiscussionCommands(projectId);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (focusOnMount) {
      article.current?.focus();
    }
  }, [focusOnMount]);

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
      className="flex gap-2.5 rounded-lg focus:shadow-focus focus:outline-none"
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
            initial={comment.body ?? ''}
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
          <CommentBody text={comment.body ?? ''} />
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
  initial: string;
  saving: boolean;
  onSave: (body: string) => void;
  onCancel: () => void;
}

function EditForm({ initial, saving, onSave, onCancel }: EditFormProps) {
  const [text, setText] = useState(initial);
  return (
    <div className="flex flex-col gap-2">
      <textarea
        aria-label="Edit comment"
        value={text}
        rows={3}
        autoFocus
        onChange={(event) => {
          setText(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            onSave(text);
          }
        }}
        className="w-full resize-y rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-fg focus:border-accent focus:shadow-focus focus:outline-none"
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="primary"
          disabled={saving || text.trim() === ''}
          onClick={() => {
            onSave(text);
          }}
        >
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}
