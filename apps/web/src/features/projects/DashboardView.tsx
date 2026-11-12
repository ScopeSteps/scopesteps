import { Link } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { ButtonLink } from '@/components/ButtonLink';
import { EmptyState } from '@/components/EmptyState';
import { Meter } from '@/components/Meter';
import { StatTile } from '@/components/StatTile';
import { Tag } from '@/components/Tag';
import { changeRequestName, changeRequestStatus } from '@/features/change-control';
import { roleName } from '@/features/identity';
import { describeError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

import { coveredPercent, formatWait } from './dashboard';
import type { Dashboard } from './dashboard';
import { useDashboard } from './useDashboard';

/** Where each figure's details are, from the page that shows the dashboard. */
export interface DashboardLinks {
  backlog: (versionId?: string) => string;
  chat: string;
  changes: string;
  team: string;
  sources: string;
}

interface DashboardViewProps {
  projectId: string;
  links: DashboardLinks;
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

/** The project's figures as tiles, who things wait on, open questions and the version timeline. */
export function DashboardView({ projectId, links }: DashboardViewProps) {
  const { data, error, isPending, refetch } = useDashboard(projectId);

  if (isPending) {
    return (
      <p role="status" className="text-subtle">
        Loading the dashboard…
      </p>
    );
  }
  if (error) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the dashboard. {describeError(error)}
      </Banner>
    );
  }
  if (!data.has_sources) {
    return (
      <EmptyState
        title="Nothing to show yet"
        action={
          <ButtonLink variant="primary" to={links.sources}>
            Add a source
          </ButtonLink>
        }
      >
        <p>
          Start by adding the project’s brief, meeting notes or transcripts. Then ask the agent for
          a backlog in the chat. The figures show here as the work moves on.
        </p>
      </EmptyState>
    );
  }
  return <Figures dashboard={data} links={links} />;
}

function Figures({ dashboard, links }: { dashboard: Dashboard; links: DashboardLinks }) {
  const { counts, coverage, open_questions: questions, change_requests: requests } = dashboard;
  const status = dashboard.status;
  const inReview = requests.by_status.find((row) => row.status === 'in_review')?.count ?? 0;
  const latest = dashboard.timeline.at(-1);
  const oldest = questions.oldest[0];

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="dashboard-figures" className="flex flex-col gap-3">
        <h2 id="dashboard-figures" className="sr-only">
          Figures
        </h2>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
          <StatTile
            label="Approved version"
            value={
              status.baseline_version === null ? 'None yet' : `v${String(status.baseline_version)}`
            }
            detail={
              latest
                ? `Approved ${formatWhen(latest.approved_at)} by ${latest.approved_by_name}`
                : 'Nothing is approved yet'
            }
            to={links.backlog(status.baseline_version_id ?? undefined)}
          />
          <StatTile
            label={counts?.approved === false ? 'Stories in the draft' : 'Stories'}
            value={counts ? counts.stories : '–'}
            detail={
              counts
                ? `${plural(counts.epics, 'epic')} · ${plural(counts.tasks, 'task')}`
                : 'No backlog yet'
            }
            to={links.backlog(counts?.version_id)}
          />
          {coverage && (
            <StatTile
              label="Requirements covered"
              value={`${String(coveredPercent(coverage.covered, coverage.confirmed))}%`}
              detail={`${String(coverage.covered)} of ${plural(coverage.confirmed, 'confirmed requirement')}${
                coverage.version_number === null
                  ? ', in the draft'
                  : `, as drafted for v${String(coverage.version_number)}`
              }`}
              to={links.backlog(
                dashboard.timeline.find((entry) => entry.number === coverage.version_number)
                  ?.version_id ?? counts?.version_id,
              )}
            >
              <Meter
                label="Requirements covered"
                value={coverage.covered}
                max={coverage.confirmed}
                valueText={`${String(coverage.covered)} of ${String(coverage.confirmed)}`}
              />
            </StatTile>
          )}
          <StatTile
            label="Open questions"
            value={questions.count}
            detail={
              oldest?.waited_seconds != null
                ? `Oldest waiting ${formatWait(oldest.waited_seconds)}`
                : questions.count === 0
                  ? 'Nothing waits for an answer'
                  : 'Waiting for an answer'
            }
            to={links.chat}
          />
          <StatTile
            label="Change requests"
            value={requests.total}
            detail={inReview > 0 ? `${String(inReview)} in review` : 'None in review'}
            to={links.changes}
          />
          <StatTile
            label="Average time to a decision"
            value={
              requests.average_seconds_to_decision === null
                ? '–'
                : formatWait(requests.average_seconds_to_decision)
            }
            detail={
              requests.decided === 0
                ? 'No change request decided yet'
                : `Over ${plural(requests.decided, 'decided change request')}`
            }
            to={links.changes}
          />
        </div>
      </section>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,320px),1fr))] gap-6">
        <section aria-labelledby="dashboard-waiting" className="flex flex-col gap-2">
          <h2 id="dashboard-waiting" className="text-[15px] font-semibold">
            Who things wait on
          </h2>
          {dashboard.waiting_on.length === 0 ? (
            <p className="text-[13px] text-subtle">Nothing waits on anyone right now.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-xl border border-line bg-surface p-0">
              {dashboard.waiting_on.map((person) => (
                <li key={person.user_id}>
                  <Link
                    to={links.team}
                    className="flex items-center gap-2 px-3.5 py-2.5 text-fg no-underline hover:bg-hover"
                  >
                    <span className="min-w-0 flex-1 truncate">{person.display_name}</span>
                    <Tag>{roleName(person.role)}</Tag>
                    <span className="font-mono text-[13px] tabular-nums">
                      {plural(person.waiting, 'item')} waiting
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="dashboard-questions" className="flex flex-col gap-2">
          <h2 id="dashboard-questions" className="text-[15px] font-semibold">
            Questions waiting longest
          </h2>
          {questions.oldest.length === 0 ? (
            <p className="text-[13px] text-subtle">The agent has no question waiting.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-xl border border-line bg-surface p-0">
              {questions.oldest.map((question) => (
                <li key={question.id}>
                  <Link
                    to={links.chat}
                    className="flex flex-wrap items-baseline gap-2 px-3.5 py-2.5 text-fg no-underline hover:bg-hover"
                  >
                    <span className="min-w-0 flex-1">{question.subject}</span>
                    <span className="text-xs text-subtle">
                      {question.waited_seconds === null
                        ? 'Waiting'
                        : `Waiting ${formatWait(question.waited_seconds)}`}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="dashboard-requests" className="flex flex-col gap-2">
          <h2 id="dashboard-requests" className="text-[15px] font-semibold">
            Change requests by status
          </h2>
          <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-xl border border-line bg-surface p-0">
            {requests.by_status.map((row) => (
              <li key={row.status}>
                <Link
                  to={links.changes}
                  className="flex items-center gap-2 px-3.5 py-2 text-fg no-underline hover:bg-hover"
                >
                  <span className="flex-1">
                    <Tag tone={changeRequestStatus(row.status).tone}>
                      {changeRequestStatus(row.status).label}
                    </Tag>
                  </span>
                  <span className="font-mono text-[13px] tabular-nums">{row.count}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="dashboard-timeline" className="flex flex-col gap-2">
          <h2 id="dashboard-timeline" className="text-[15px] font-semibold">
            Approved versions
          </h2>
          {dashboard.timeline.length === 0 ? (
            <p className="text-[13px] text-subtle">
              Approved versions show here, oldest first, once v1 is approved on the Backlog.
            </p>
          ) : (
            <ol className="m-0 flex list-none flex-col gap-0 p-0">
              {dashboard.timeline.map((entry) => (
                <li key={entry.version_id} className="relative border-l-2 border-line pb-3 pl-4">
                  <span
                    aria-hidden="true"
                    className="absolute top-1 -left-[5px] size-2 rounded-full bg-accent"
                  />
                  <Link
                    to={links.backlog(entry.version_id)}
                    className="font-mono font-semibold text-accent-ink tabular-nums underline"
                  >
                    v{entry.number}
                  </Link>
                  <p className="text-[13px] text-muted">
                    Approved by {entry.approved_by_name}, {formatWhen(entry.approved_at)}
                    {entry.change_request_number !== null && (
                      <>, from {changeRequestName(entry.change_request_number)}</>
                    )}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
