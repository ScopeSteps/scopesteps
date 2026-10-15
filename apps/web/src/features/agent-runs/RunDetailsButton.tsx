import { useRef, useState } from 'react';
import type { RefObject } from 'react';

import { IconButton } from '@/components/IconButton';
import { useLayer } from '@/components/useLayer';

import type { Run } from './types';

const STATUS_LABELS: Record<Run['status'], string> = {
  created: 'Working',
  running: 'Working',
  waiting_for_input: 'Waiting for you',
  ready_for_review: 'Draft ready',
  failed: 'Failed',
  cancelled: 'Stopped',
  completed: 'Replied',
};

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2.5">
      <dt>{label}</dt>
      <dd
        className={mono ? 'text-right font-mono font-medium break-all tabular-nums' : 'text-right'}
      >
        {value}
      </dd>
    </div>
  );
}

interface PopoverProps {
  run: Run;
  trigger: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
}

function RunDetailsPopover({ run, trigger, onClose }: PopoverProps) {
  const popover = useRef<HTMLDivElement>(null);
  useLayer(popover, { onClose, returnFocus: trigger, trapFocus: false });
  const { usage, limits } = run;

  return (
    <div
      ref={popover}
      role="dialog"
      aria-label="Run details"
      tabIndex={-1}
      onBlur={(event) => {
        // Focus left the popover: it does not stay open behind whatever has focus now.
        if (!event.currentTarget.contains(event.relatedTarget)) {
          onClose();
        }
      }}
      className="absolute top-[42px] right-0 z-[25] flex w-[min(280px,calc(100vw-24px))] flex-col gap-2 rounded-xl border border-line bg-surface px-3.5 py-3 text-[13px] shadow-pop"
    >
      <strong className="font-semibold">Agent run</strong>
      <dl className="m-0 flex flex-col gap-2">
        <Row label="Run" value={run.id} />
        <Row label="Status" value={STATUS_LABELS[run.status]} mono={false} />
        <Row
          label="Model turns"
          value={`${String(usage.model_turns)} / ${String(limits.max_turns)}`}
        />
        <Row
          label="Tool calls"
          value={`${String(usage.tool_calls)} / ${String(limits.max_tool_calls)}`}
        />
        <Row
          label="Question rounds"
          value={`${String(usage.clarification_rounds)} / ${String(limits.max_clarification_rounds)}`}
        />
        <Row
          label="Tokens"
          value={`${usage.total_tokens.toLocaleString()} / ${limits.max_total_tokens.toLocaleString()}`}
        />
        <Row
          label="Estimated cost"
          value={`$${usage.cost_usd_estimate}${limits.max_cost_usd ? ` / $${limits.max_cost_usd}` : ''}`}
        />
        <Row label="Model" value={`${run.provider} · ${run.model_id}`} />
      </dl>
      {run.fallback_reason && (
        <p className="text-xs text-subtle">Backup provider in use: {run.fallback_reason}</p>
      )}
      <span className="text-xs text-subtle">Limits stop the agent from looping.</span>
    </div>
  );
}

/** The run's id, status, usage and limits, as the API reports them, behind an info button. */
export function RunDetailsButton({ run }: { run: Run }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  return (
    <div className="relative">
      <IconButton
        ref={trigger}
        icon="info"
        label="Run details"
        aria-expanded={open}
        // The popover closes itself when focus leaves it; without this the same click reopens it.
        onMouseDown={(event) => {
          if (open) {
            event.preventDefault();
          }
        }}
        onClick={() => {
          setOpen((current) => !current);
        }}
      />
      {open && (
        <RunDetailsPopover
          run={run}
          trigger={trigger}
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </div>
  );
}
