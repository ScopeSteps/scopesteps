import { useSearchParams } from 'react-router';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { useCanEdit } from '@/features/identity';
import { useProject } from '@/features/projects';
import { describeError } from '@/lib/apiError';

import { AddSourceButton } from './AddSourceButton';
import { SourcesTable } from './SourcesTable';
import { SourceViewer } from './SourceViewer';
import { useSources } from './useSources';
import { WordMeter } from './WordMeter';

export function SourcesView({ projectId }: { projectId: string }) {
  const { data: versions, error, isPending, refetch } = useSources(projectId);
  const { data: project } = useProject(projectId);
  const canEdit = useCanEdit(projectId);
  const [searchParams, setSearchParams] = useSearchParams();
  // The viewer's version and paragraph live in the URL, so citations can link to them.
  const openVersionId = searchParams.get('version');
  const totalWords = versions?.reduce((total, version) => total + version.word_count, 0) ?? 0;

  return (
    <section aria-labelledby="stored-sources-heading" className="flex flex-col gap-4">
      <h2 id="stored-sources-heading" className="sr-only">
        Stored sources
      </h2>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {versions && <WordMeter words={totalWords} limits={project?.limits.source} />}
        {canEdit && (
          <span className="ml-auto">
            <AddSourceButton projectId={projectId} />
          </span>
        )}
      </div>

      {isPending && (
        <p role="status" className="text-subtle">
          Loading sources…
        </p>
      )}
      {error && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void refetch()}>
              Try again
            </Button>
          }
        >
          Could not load the stored sources. {describeError(error)}
        </Banner>
      )}
      {versions?.length === 0 && (
        <EmptyState title="No sources yet">
          <p>
            Add a project brief and a meeting transcript. The agent works only from these files and
            your answers.
          </p>
        </EmptyState>
      )}
      {versions && versions.length > 0 && (
        <>
          <SourcesTable versions={versions} />
          <p className="text-xs text-subtle">
            Your answers to the agent&apos;s questions are saved as evidence too, and stories can
            cite them like a source.
          </p>
        </>
      )}

      {openVersionId && (
        <SourceViewer
          projectId={projectId}
          sourceVersionId={openVersionId}
          version={versions?.find((version) => version.id === openVersionId)}
          versionsLoaded={versions !== undefined}
          selectedBlockId={searchParams.get('block')}
          canRemove={canEdit}
          onClose={() => {
            setSearchParams({});
          }}
        />
      )}
    </section>
  );
}
