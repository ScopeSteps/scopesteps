import { useSearchParams } from 'react-router';

import { describeError } from '@/lib/apiError';

import { SourceBlocks } from './SourceBlocks';
import { SourceUploadForm } from './SourceUploadForm';
import { SourceVersionList } from './SourceVersionList';
import { KIND_LABELS } from './types';
import { useSources } from './useSources';

export function SourcesView({ projectId }: { projectId: string }) {
  const { data: versions, error, isPending, refetch } = useSources(projectId);
  const [searchParams, setSearchParams] = useSearchParams();

  // A link may point at a superseded version, which the list of current versions lacks.
  const selectedVersionId = searchParams.get('version') ?? versions?.[0]?.id;
  const selectedVersion = versions?.find((version) => version.id === selectedVersionId);

  return (
    <div className="space-y-8">
      <SourceUploadForm
        projectId={projectId}
        onUploaded={(uploaded) => {
          const first = uploaded[0];
          if (first) {
            setSearchParams({ version: first.id });
          }
        }}
      />

      <section aria-labelledby="stored-sources-heading">
        <h2 id="stored-sources-heading" className="text-lg font-semibold">
          Stored sources
        </h2>
        <div className="mt-3">
          {isPending && <p role="status">Loading sources…</p>}
          {error && (
            <div role="alert" className="text-sm text-bad-ink">
              <p>Could not load the stored sources. {describeError(error)}</p>
              <button type="button" onClick={() => void refetch()} className="mt-2 underline">
                Try again
              </button>
            </div>
          )}
          {versions?.length === 0 && (
            <p className="text-sm text-muted">
              No sources yet. Upload a project brief and a meeting transcript to begin.
            </p>
          )}
          {versions && versions.length > 0 && (
            <SourceVersionList versions={versions} selectedVersionId={selectedVersionId} />
          )}
        </div>
      </section>

      {selectedVersionId && (
        <section aria-labelledby="paragraphs-heading">
          <h2 id="paragraphs-heading" className="text-lg font-semibold">
            {selectedVersion
              ? `${KIND_LABELS[selectedVersion.kind]}: ${selectedVersion.filename}, version ${String(selectedVersion.version)}`
              : 'Source paragraphs'}
          </h2>
          {versions && !selectedVersion && (
            <p className="mt-1 text-sm text-muted">
              Version <span className="font-mono">{selectedVersionId}</span> is not the current
              version of a source.
            </p>
          )}
          <div className="mt-3">
            <SourceBlocks
              projectId={projectId}
              sourceVersionId={selectedVersionId}
              selectedBlockId={searchParams.get('block')}
            />
          </div>
        </section>
      )}
    </div>
  );
}
