import { useId, useLayoutEffect, useRef } from 'react';
import type { KeyboardEvent, RefObject } from 'react';

import { Icon } from '@/components/Icon';
import { useLayer } from '@/components/useLayer';
import { describeError } from '@/lib/apiError';

import { useProjects } from './useProjects';

const ITEM_CLASSES =
  'flex min-h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-left hover:bg-hover';

interface ProjectMenuProps {
  currentProjectId: string;
  /** The button that opened the menu; focus returns to it. */
  trigger: RefObject<HTMLElement | null>;
  onClose: () => void;
  onSwitch: (projectId: string) => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
}

/**
 * The open project switcher: the user's projects as the API lists them, the current one
 * checked, then New project and Project settings. Arrow keys, Home and End move between items.
 */
export function ProjectMenu({
  currentProjectId,
  trigger,
  onClose,
  onSwitch,
  onNewProject,
  onOpenSettings,
}: ProjectMenuProps) {
  const { data: projects, error, isPending, refetch } = useProjects();
  const menu = useRef<HTMLDivElement>(null);
  const currentItem = useRef<HTMLButtonElement>(null);
  const retryItem = useRef<HTMLButtonElement>(null);
  const headingId = useId();
  const loadingId = useId();
  const errorId = useId();
  // Focus starts on the current project; on the menu itself while the list is loading.
  useLayer(menu, { onClose, initialFocus: currentItem, returnFocus: trigger, trapFocus: false });
  const listed = projects !== undefined;
  const failed = error !== null;
  // When the list arrives or fails, focus moves to the current project or to the retry, which
  // reads out the reason. Until then it is on the menu, or on the page when the retry that had
  // it was replaced.
  useLayoutEffect(() => {
    const active = document.activeElement;
    if (active === menu.current || active === document.body || active === null) {
      (listed ? currentItem : retryItem).current?.focus();
    }
  }, [listed, failed]);

  function moveFocus(event: KeyboardEvent) {
    const items = [...(menu.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])];
    const last = items.length - 1;
    const current = items.findIndex((item) => item === document.activeElement);
    let next: number;
    switch (event.key) {
      case 'ArrowDown':
        next = current === last ? 0 : current + 1;
        break;
      case 'ArrowUp':
        next = current <= 0 ? last : current - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    items[next]?.focus();
  }

  function closeIfFocusLeft() {
    if (menu.current && !menu.current.contains(document.activeElement)) {
      onClose();
    }
  }

  return (
    <div
      ref={menu}
      role="menu"
      aria-label="Projects"
      aria-busy={isPending}
      aria-describedby={isPending ? loadingId : undefined}
      tabIndex={-1}
      onKeyDown={moveFocus}
      // A menu does not stay open behind focus that left it (Tab, or a click elsewhere). Focus
      // also leaves for a moment when the focused item is replaced, or when React re-runs the
      // layer's effects in development, so this decides only once focus has settled.
      onBlur={() => {
        window.setTimeout(closeIfFocusLeft);
      }}
      className="absolute inset-x-0 top-[calc(100%+6px)] z-[25] flex max-h-[min(420px,70vh)] flex-col overflow-auto rounded-xl border border-line bg-surface p-1.5 shadow-pop"
    >
      {/* A menu may hold only items, groups and separators, so its states are plain text. */}
      <div role="group" aria-labelledby={headingId} className="flex flex-col">
        <span
          id={headingId}
          className="px-2.5 pt-1.5 pb-0.5 text-[11px] font-semibold tracking-[0.07em] text-subtle uppercase"
        >
          Your projects
        </span>
        {isPending && (
          <p id={loadingId} className="px-2.5 py-2 text-[13px] text-subtle">
            Loading your projects…
          </p>
        )}
        {error && (
          <>
            <p id={errorId} className="px-2.5 pt-2 pb-1 text-[13px] text-bad-ink">
              Could not load your projects. {describeError(error)}
            </p>
            <button
              ref={retryItem}
              type="button"
              role="menuitem"
              aria-describedby={errorId}
              onClick={() => void refetch()}
              className={ITEM_CLASSES}
            >
              <span className="flex w-4 flex-none" />
              Try again
            </button>
          </>
        )}
        {projects?.map((project) => {
          const isCurrent = project.id === currentProjectId;
          return (
            <button
              key={project.id}
              ref={isCurrent ? currentItem : undefined}
              type="button"
              role="menuitemradio"
              aria-checked={isCurrent}
              onClick={() => {
                onSwitch(project.id);
              }}
              className={ITEM_CLASSES}
            >
              <span className="flex w-4 flex-none">
                {isCurrent && <Icon name="check" size={16} />}
              </span>
              <span className="min-w-0 flex-1 truncate">{project.name}</span>
            </button>
          );
        })}
      </div>
      <button type="button" role="menuitem" onClick={onNewProject} className={ITEM_CLASSES}>
        <Icon name="plus" size={16} />
        New project
      </button>
      <div role="separator" className="mx-1 my-1.5 border-t border-line" />
      <button type="button" role="menuitem" onClick={onOpenSettings} className={ITEM_CLASSES}>
        <Icon name="settings" size={16} />
        Project settings
      </button>
    </div>
  );
}
