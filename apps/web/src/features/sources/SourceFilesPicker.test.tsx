import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';

import { SourceFilesPicker } from './SourceFilesPicker';
import type { SourceFile, SourceKind } from './types';

const LIMITS = { max_bytes: 64, max_words: 6000 };

const LATER = 'No files yet. You can also add sources after the project is created.';

function Harness({
  error = null,
  heldKinds = [],
}: {
  error?: string | null;
  heldKinds?: SourceKind[];
}) {
  const [files, setFiles] = useState<SourceFile[]>([]);
  return (
    <main>
      <SourceFilesPicker
        files={files}
        onChange={setFiles}
        limits={LIMITS}
        error={error}
        heldKinds={heldKinds}
        emptyHint={LATER}
      />
      <output aria-label="Chosen">
        {files.map((entry) => `${entry.kind}:${entry.file.name}`).join(' ')}
      </output>
    </main>
  );
}

function choose(...files: File[]) {
  fireEvent.change(screen.getByLabelText('Upload .txt or .md files'), { target: { files } });
}

describe('SourceFilesPicker', () => {
  it('starts with the hint it is given and the limits from the API', async () => {
    render(<Harness />);

    expect(screen.getByText(LATER)).toBeInTheDocument();
    expect(
      screen.getByText(/Up to 64 bytes per file and 6,000 words across all sources\./),
    ).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('takes several files, suggesting brief, transcript, then supporting document', async () => {
    render(<Harness />);

    choose(new File(['a'], 'brief.md'), new File(['b'], 'call.txt'), new File(['c'], 'email.md'));

    const list = within(screen.getByRole('list', { name: 'Files to add' }));
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'brief:brief.md transcript:call.txt supporting_document:email.md',
    );
    await expectNoAccessibilityViolations();
  });

  it('carries the suggestions on from the kinds the project already holds', () => {
    render(<Harness heldKinds={['brief']} />);

    choose(new File(['b'], 'call.txt'), new File(['c'], 'email.md'));

    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'transcript:call.txt supporting_document:email.md',
    );
  });

  it('lets each file’s kind be changed and a file be taken off the list', async () => {
    render(<Harness />);
    choose(new File(['a'], 'brief.md'), new File(['b'], 'call.txt'));

    await userEvent.selectOptions(screen.getByLabelText('Type of call.txt'), 'Supporting document');
    await userEvent.click(screen.getByRole('button', { name: 'Remove brief.md' }));

    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'supporting_document:call.txt',
    );
  });

  it('refuses files the browser can tell are wrong and keeps the rest', () => {
    render(<Harness />);

    choose(
      new File(['a'], 'brief.md'),
      new File(['%PDF'], 'scan.pdf'),
      new File(['x'.repeat(65)], 'long.txt'),
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('scan.pdf is not a .txt or .md file.');
    expect(alert).toHaveTextContent('long.txt is larger than 64 bytes.');
    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent('brief:brief.md');
    expect(screen.getByLabelText('Upload .txt or .md files')).toBeInvalid();
  });

  it('shows the server’s answer to the last upload', () => {
    render(<Harness error="Adding these files would go over the word limit." />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Adding these files would go over the word limit.',
    );
  });
});
