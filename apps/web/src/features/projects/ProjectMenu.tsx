import { useEffect, useRef } from 'react';
import type { KeyboardEvent, RefObject } from 'react';

import { Button } from '@/components/Button';
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
 * checked, then New project and Project settings. Arrow keys move between items.
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
  // Focus starts on the current project; on the menu itself while the list is loading.
  useLayer(menu, { onClose, initialFocus: currentItem, returnFocus: trigger, trapFocus: false });
  const listed = projects !== undefined;
  useEffect(() => {
    if (listed && document.activeElement === menu.current) {
      currentItem.current?.focus();
    }
  }, [listed]);

  function moveFocus(event: KeyboardEvent) {
    const items = [...(menu.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]') ?? [])];
    const current = items.findIndex((item) => item === document.activeElement);
    const step = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (step === 0 || items.length === 0) {
      return;
    }
    event.preventDefault();
    items.at((current + step) % items.length)?.focus();
  }

  return (
    <div
      ref={menu}
      role="menu"
      aria-label="Projects"
      aria-busy={isPending}
      tabIndex={-1}
      onKeyDown={moveFocus}
      onBlur={(event) => {
        // Focus left the menu (Tab, or a click elsewhere): a menu does not stay open behind it.
        if (!event.currentTarget.contains(event.relatedTarget)) {
          onClose();
        }
      }}
      className="absolute inset-x-0 top-[calc(100%+6px)] z-[25] flex max-h-[min(420px,70vh)] flex-col overflow-auto rounded-xl border border-line bg-surface p-1.5 shadow-pop"
    >
      <span
        aria-hidden="true"
        className="px-2.5 pt-1.5 pb-0.5 text-[11px] font-semibold tracking-[0.07em] text-subtle uppercase"
      >
        Your projects
      </span>
      {isPending && (
        <p role="status" className="px-2.5 py-2 text-[13px] text-subtle">
          Loading your projects…
        </p>
      )}
      {error && (
        <div role="alert" className="flex flex-col items-start gap-1.5 px-2.5 py-2 text-[13px]">
          <span className="text-bad-ink">Could not load your projects. {describeError(error)}</span>
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
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
