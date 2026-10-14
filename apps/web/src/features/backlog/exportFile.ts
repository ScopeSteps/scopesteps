export type ExportFormat = 'json' | 'markdown';

/** What the export endpoint returned, kept byte for byte so preview, copy and file agree. */
export interface ExportFile {
  text: string;
  /** The download name from `Content-Disposition`; null if the server sent none. */
  filename: string | null;
  mediaType: string;
}

export function attachmentFilename(contentDisposition: string | null): string | null {
  const match = /filename="([^"]+)"|filename=([^;\s]+)/i.exec(contentDisposition ?? '');
  return match?.[1] ?? match?.[2] ?? null;
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
