import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { speakersQueryKey } from './speakers';
import { useSpeakers } from './useSpeakers';
import { WhosWhoModal } from './WhosWhoModal';

interface UploadedTranscript {
  sourceId: string;
  sourceName: string;
}

interface WhosWhoAfterUploadProps {
  projectId: string;
  /** The transcripts an upload just added, in the order they were added. */
  transcripts: readonly UploadedTranscript[];
  onDone: () => void;
}

/**
 * Opens Who's who for each newly added transcript in which speakers were found, one after
 * another. A transcript without speaker labels is passed over; closing one moves to the next.
 */
export function WhosWhoAfterUpload({ projectId, transcripts, onDone }: WhosWhoAfterUploadProps) {
  const queryClient = useQueryClient();
  const speakers = useSpeakers(projectId);
  const [fresh, setFresh] = useState(false);
  const [index, setIndex] = useState(0);

  // The cached list was read before the upload, so it does not know the new transcripts yet.
  useEffect(() => {
    let current = true;
    void queryClient.invalidateQueries({ queryKey: speakersQueryKey(projectId) }).then(() => {
      if (current) {
        setFresh(true);
      }
    });
    return () => {
      current = false;
    };
  }, [queryClient, projectId]);

  const withSpeakers = fresh
    ? transcripts.filter((uploaded) =>
        speakers.data?.some(
          (transcript) =>
            transcript.source_id === uploaded.sourceId && transcript.speakers.length > 0,
        ),
      )
    : [];
  const showing = withSpeakers[index];
  const finished = fresh && (speakers.isError || (speakers.data !== undefined && !showing));

  useEffect(() => {
    if (finished) {
      onDone();
    }
  }, [finished, onDone]);

  if (!showing) {
    return null;
  }
  return (
    <WhosWhoModal
      key={showing.sourceId}
      projectId={projectId}
      sourceId={showing.sourceId}
      sourceName={showing.sourceName}
      onClose={() => {
        setIndex((count) => count + 1);
      }}
    />
  );
}
