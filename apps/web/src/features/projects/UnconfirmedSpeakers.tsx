import { useState } from 'react';

import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { sourceLabel, useSources } from '@/features/sources';

import type { UnconfirmedSpeaker } from './people';
import { useUnconfirmedSpeakers } from './usePeople';
import { WhosWhoModal } from './WhosWhoModal';

interface Transcript {
  sourceId: string;
  name: string;
  speakers: UnconfirmedSpeaker[];
}

/**
 * The speakers in current transcripts nobody has said who they are, by transcript, each with a
 * way into Who's who. Renders nothing once every speaker is confirmed or marked not a person.
 */
export function UnconfirmedSpeakers({ projectId }: { projectId: string }) {
  const { data: unconfirmed } = useUnconfirmedSpeakers(projectId);
  const { data: sources } = useSources(projectId);
  const [open, setOpen] = useState<Transcript | null>(null);

  if (!unconfirmed || unconfirmed.length === 0) {
    return null;
  }
  const transcripts: Transcript[] = [];
  for (const speaker of unconfirmed) {
    let transcript = transcripts.find((each) => each.sourceId === speaker.source_id);
    if (!transcript) {
      const version = sources?.find((each) => each.source_id === speaker.source_id);
      transcript = {
        sourceId: speaker.source_id,
        name: version
          ? `${sourceLabel(version.source_number)} ${version.filename}`
          : 'A transcript',
        speakers: [],
      };
      transcripts.push(transcript);
    }
    transcript.speakers.push(speaker);
  }
  const count = unconfirmed.length;

  return (
    <section
      aria-labelledby="unconfirmed-speakers-heading"
      className="flex flex-col gap-2.5 rounded-[10px] border border-warn-line bg-warn-soft px-3.5 py-3 text-[13px] text-warn-ink"
    >
      <h3 id="unconfirmed-speakers-heading" className="flex items-center gap-2 font-semibold">
        <Icon name="warn" size={16} />
        {count} {count === 1 ? 'speaker' : 'speakers'} to confirm
      </h3>
      <p>
        Nobody has said who {count === 1 ? 'this speaker is' : 'these speakers are'} yet, so the
        agent treats them as role unknown. Runs are never held up.
      </p>
      <ul aria-label="Transcripts with speakers to confirm" className="m-0 list-none p-0">
        {transcripts.map((transcript) => (
          <li
            key={transcript.sourceId}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-warn-line py-2 first:border-t-0"
          >
            <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">
              <span className="font-semibold">{transcript.name}</span>:{' '}
              {transcript.speakers.map((speaker) => speaker.label).join(', ')}
            </span>
            <Button
              size="sm"
              aria-label={`Who's who in ${transcript.name}`}
              onClick={() => {
                setOpen(transcript);
              }}
            >
              Who&apos;s who
            </Button>
          </li>
        ))}
      </ul>
      {open && (
        <WhosWhoModal
          projectId={projectId}
          sourceId={open.sourceId}
          sourceName={open.name}
          onClose={() => {
            setOpen(null);
          }}
        />
      )}
    </section>
  );
}
