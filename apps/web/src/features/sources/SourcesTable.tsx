import { Link } from 'react-router';

import { Button } from '@/components/Button';
import { Tag } from '@/components/Tag';
import { confirmedCount } from '@/features/projects';
import type { TranscriptSpeakers } from '@/features/projects';
import { cx } from '@/lib/cx';

import { formatAddedAt, plural } from './format';
import { KIND_LABELS, sourceLabel } from './types';
import type { SourceVersion } from './types';

interface SourcesTableProps {
  versions: SourceVersion[];
  /** The speakers found in each transcript; a transcript with any offers Who's who. */
  speakers?: readonly TranscriptSpeakers[] | undefined;
  onOpenWhosWho?: (version: SourceVersion) => void;
}

export function SourcesTable({ versions, speakers, onOpenWhosWho }: SourcesTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[34rem] border-collapse text-sm">
        <caption className="sr-only">Stored sources</caption>
        <thead>
          <tr>
            {['Source', 'Type', 'Size', 'Added'].map((column) => (
              <th
                key={column}
                scope="col"
                className="border-b border-line bg-surface-2 px-3.5 py-2.5 text-left text-xs font-semibold text-subtle"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {versions.map((version) => (
            <tr key={version.id} className="border-b border-line last:border-b-0">
              <td className="px-3.5 py-3 align-top">
                <span className="flex items-center gap-2">
                  <Tag tone="accent" className="font-mono tabular-nums">
                    {sourceLabel(version.source_number)}
                  </Tag>
                  <Link
                    to={{ search: `?version=${version.id}` }}
                    className="font-semibold [overflow-wrap:anywhere] text-fg hover:text-accent-ink hover:underline"
                  >
                    {version.filename}
                  </Link>
                  {version.version > 1 && (
                    <span className="font-mono text-xs text-subtle tabular-nums">
                      v{version.version}
                    </span>
                  )}
                </span>
                {onOpenWhosWho && (
                  <SpeakerSummary
                    version={version}
                    transcript={speakers?.find((each) => each.source_id === version.source_id)}
                    onOpen={onOpenWhosWho}
                  />
                )}
              </td>
              <td className="px-3.5 py-3 align-top">{KIND_LABELS[version.kind]}</td>
              <td className="px-3.5 py-3 align-top font-mono text-[13px] whitespace-nowrap tabular-nums">
                {plural(version.block_count, '¶', '¶')} · {plural(version.word_count, 'word')}
              </td>
              <td className="px-3.5 py-3 align-top text-xs whitespace-nowrap text-subtle">
                <time dateTime={version.created_at}>{formatAddedAt(version.created_at)}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface SpeakerSummaryProps {
  version: SourceVersion;
  transcript: TranscriptSpeakers | undefined;
  onOpen: (version: SourceVersion) => void;
}

/** How many of a transcript's speakers are confirmed, as the way into its Who's who. */
function SpeakerSummary({ version, transcript, onOpen }: SpeakerSummaryProps) {
  if (!transcript || transcript.speakers.length === 0) {
    return null;
  }
  const total = transcript.speakers.length;
  const confirmed = confirmedCount(transcript);
  const summary = `${String(confirmed)} of ${String(total)} ${total === 1 ? 'speaker' : 'speakers'} confirmed`;
  return (
    <Button
      size="sm"
      variant="ghost"
      className={cx('mt-1.5 -ml-2', confirmed < total && 'text-warn-ink')}
      aria-label={`Who's who in ${sourceLabel(version.source_number)} ${version.filename}: ${summary}`}
      onClick={() => {
        onOpen(version);
      }}
    >
      {summary}
    </Button>
  );
}
