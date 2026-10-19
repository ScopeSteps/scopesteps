/** What the export endpoint returned, kept byte for byte so the preview and the saved file agree. */
export interface ExportFile {
  text: string;
  /** The download name from `Content-Disposition`; null if the server sent none. */
  filename: string | null;
  mediaType: string;
}

/** One row of the Jira CSV, with each cell exactly as the file holds it. */
export interface JiraRow {
  issueId: string;
  issueType: string;
  summary: string;
  description: string;
  parent: string;
}

const JIRA_COLUMNS = ['Issue ID', 'Issue Type', 'Summary', 'Description', 'Parent'];

export function attachmentFilename(contentDisposition: string | null): string | null {
  const match = /filename="([^"]+)"|filename=([^;\s]+)/i.exec(contentDisposition ?? '');
  return match?.[1] ?? match?.[2] ?? null;
}

/**
 * Splits RFC 4180 text into rows of cells: quoted cells may hold commas, line breaks and doubled
 * quotes. Returns null when a quote is never closed.
 */
export function parseCsv(text: string): string[][] | null {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  let index = 0;
  while (index < text.length) {
    const char = text.charAt(index);
    index += 1;
    if (quoted) {
      if (char !== '"') {
        cell += char;
      } else if (text.charAt(index) === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = false;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(cell);
      cell = '';
    } else if (char === '\n' || (char === '\r' && text.charAt(index) === '\n')) {
      index += char === '\r' ? 1 : 0;
      rows.push([...row, cell]);
      row = [];
      cell = '';
    } else {
      cell += char;
    }
  }
  if (quoted) {
    return null;
  }
  if (cell !== '' || row.length > 0) {
    rows.push([...row, cell]);
  }
  return rows;
}

/** The rows of a Jira CSV export, or null when the text is not one. */
export function jiraRows(text: string): JiraRow[] | null {
  const rows = parseCsv(text);
  const header = rows?.[0];
  if (!rows || header?.join('\u0000') !== JIRA_COLUMNS.join('\u0000')) {
    return null;
  }
  const items: JiraRow[] = [];
  for (const cells of rows.slice(1)) {
    const [issueId, issueType, summary, description, parent] = cells;
    if (
      cells.length !== JIRA_COLUMNS.length ||
      issueId === undefined ||
      issueType === undefined ||
      summary === undefined ||
      description === undefined ||
      parent === undefined
    ) {
      return null;
    }
    items.push({ issueId, issueType, summary, description, parent });
  }
  return items;
}

/** Hands the export to the browser as a file download under the server's name. */
export function saveExport(file: ExportFile, filename: string): void {
  const url = URL.createObjectURL(new Blob([file.text], { type: file.mediaType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next task: some browsers start reading the blob only after click returns.
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}
