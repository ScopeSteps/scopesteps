import type { components } from '@scopesteps/api-client';

import { formatBytes, plural } from '@/features/sources';

type Limits = components['schemas']['ProjectLimitsResponse'];

interface ProjectLimitsProps {
  limits: Limits;
}

/** The ceilings the API applies in this project, as it reports them. */
export function ProjectLimits({ limits }: ProjectLimitsProps) {
  const rows = [
    {
      term: 'Sources',
      detail: `TXT or Markdown, up to ${formatBytes(limits.source.max_bytes)} each and ${plural(limits.source.max_words, 'word')} per upload`,
    },
    {
      term: 'Agent runs',
      detail: `${plural(limits.run.max_turns, 'model turn')}, ${plural(limits.run.max_tool_calls, 'tool call')}, ${plural(limits.run.max_clarification_rounds, 'question round')}`,
    },
    {
      term: 'Draft backlog',
      detail: `Up to ${plural(limits.backlog.max_epics, 'epic')} and ${plural(limits.backlog.max_stories, 'story', 'stories')}`,
    },
    {
      term: 'Project name',
      detail: `Up to ${plural(limits.project_name_max_chars, 'character')}`,
    },
  ];

  return (
    <section aria-labelledby="project-limits-heading" className="flex flex-col gap-1.5">
      <h3 id="project-limits-heading" className="text-[13px] font-semibold">
        Limits for this project
      </h3>
      <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs">
        {rows.map((row) => (
          <div key={row.term} className="contents">
            <dt className="text-subtle">{row.term}</dt>
            <dd className="m-0 text-muted">{row.detail}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
