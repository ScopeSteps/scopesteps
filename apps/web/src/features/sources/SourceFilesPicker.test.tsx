import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/apiError';
import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody } from '@/test/fixtures';

import { SourceFilesPicker } from './SourceFilesPicker';
import type { SourceFile } from './types';

const LIMITS = { max_bytes: 64, max_document_bytes: 128, max_words: 6000 };

const LATER = 'No files yet. You can also add sources after the project is created.';

function Harness({ error = null }: { error?: Error | string | null }) {
  const [files, setFiles] = useState<SourceFile[]>([]);
  return (
    <main>
      <SourceFilesPicker
        files={files}
        onChange={setFiles}
        limits={LIMITS}
        error={error}
        emptyHint={LATER}
      />
      <output aria-label="Chosen">
        {files.map((entry) => `${entry.kind ?? 'none'}:${entry.file.name}`).join(' ')}
      </output>
    </main>
  );
}

function choose(...files: File[]) {
  fireEvent.change(screen.getByLabelText('Upload .txt, .md, .docx, .pdf or .vtt files'), {
    target: { files },
  });
}

describe('SourceFilesPicker', () => {
  it('starts with the hint it is given and the limits from the API', async () => {
    render(<Harness />);

    expect(screen.getByText(LATER)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Up to 64 bytes per text file, 128 bytes per Word, PDF or \.vtt file, and 6,000 words across all sources\./,
      ),
    ).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('takes several files, each with no kind until the person picks one', async () => {
    render(<Harness />);

    choose(new File(['a'], 'brief.md'), new File(['b'], 'call.txt'), new File(['c'], 'email.md'));

    const list = within(screen.getByRole('list', { name: 'Files to add' }));
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'none:brief.md none:call.txt none:email.md',
    );
    expect(screen.getByLabelText('Type of call.txt')).toHaveValue('');
    expect(
      within(screen.getByLabelText('Type of call.txt'))
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Project brief', 'Meeting transcript', 'Supporting document']);
    await expectNoAccessibilityViolations();
  });

  it('never guesses a kind from the order the files are chosen in', () => {
    render(<Harness />);

    choose(new File(['a'], 'supporting-sow.md'), new File(['b'], 'transcript.md'));
    choose(new File(['c'], 'brief.md'));

    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'none:supporting-sow.md none:transcript.md none:brief.md',
    );
  });

  it('lets each file’s kind be changed and a file be taken off the list', async () => {
    render(<Harness />);
    choose(new File(['a'], 'brief.md'), new File(['b'], 'call.txt'));

    await userEvent.selectOptions(screen.getByLabelText('Type of brief.md'), 'Project brief');
    await userEvent.selectOptions(screen.getByLabelText('Type of call.txt'), 'Supporting document');
    await userEvent.selectOptions(screen.getByLabelText('Type of call.txt'), 'Meeting transcript');
    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'brief:brief.md transcript:call.txt',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Remove brief.md' }));

    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent('transcript:call.txt');
  });

  it('refuses files the browser can tell are wrong and keeps the rest', () => {
    render(<Harness />);

    choose(
      new File(['a'], 'brief.md'),
      new File(['{\\rtf1}'], 'scan.rtf'),
      new File(['x'.repeat(65)], 'long.txt'),
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('scan.rtf is not a .txt, .md, .docx, .pdf or .vtt file.');
    expect(alert).toHaveTextContent('long.txt is larger than 64 bytes.');
    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent('none:brief.md');
    expect(screen.getByLabelText('Upload .txt, .md, .docx, .pdf or .vtt files')).toBeInvalid();
  });

  it('shows the server’s answer to the last upload', () => {
    render(<Harness error="Adding these files would go over the word limit." />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Adding these files would go over the word limit.',
    );
  });

  it('takes Word, PDF and WebVTT files dropped on it', () => {
    render(<Harness />);
    const files = [
      new File(['PK'], 'brief.docx'),
      new File(['WEBVTT'], 'kickoff.vtt'),
      new File(['%PDF'], 'rooms.pdf'),
    ];

    fireEvent.drop(
      screen.getByText(/You can also drop files here/).parentElement ?? document.body,
      {
        dataTransfer: { files },
      },
    );

    expect(screen.getByRole('status', { name: 'Chosen' })).toHaveTextContent(
      'none:brief.docx none:kickoff.vtt none:rooms.pdf',
    );
  });

  it('shows a refusal that names a file next to that file', async () => {
    const refusal = new ApiError(422, {
      ...errorBody('SOURCE_SCANNED', 'scan.pdf has no text to read: it looks like scanned pages.'),
      details: { field: 'brief', filename: 'scan.pdf' },
    });
    function Refused() {
      const [files, setFiles] = useState<SourceFile[]>([
        { kind: 'brief', file: new File(['%PDF'], 'scan.pdf') },
        { kind: 'transcript', file: new File(['WEBVTT'], 'kickoff.vtt') },
      ]);
      return (
        <main>
          <SourceFilesPicker files={files} onChange={setFiles} limits={LIMITS} error={refusal} />
        </main>
      );
    }
    render(<Refused />);

    const row = within(screen.getByRole('list', { name: 'Files to add' })).getAllByRole(
      'listitem',
    )[0];
    expect(row).toBeDefined();
    expect(within(row ?? document.body).getByRole('alert')).toHaveTextContent(
      'scan.pdf has no text to read',
    );
    expect(screen.getByLabelText('Type of scan.pdf')).toHaveAccessibleDescription(
      'scan.pdf has no text to read: it looks like scanned pages.',
    );
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    await expectNoAccessibilityViolations();
  });
});
