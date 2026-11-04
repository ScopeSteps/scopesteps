# 0025. Word, PDF and WebVTT sources, converted to text when uploaded

- Status: Accepted
- Date: 2026-11-04

## Context

A source could only be a `.txt` or `.md` file. Real teams keep briefs in Word and PDF, and Teams
and Zoom save meeting transcripts as WebVTT (`.vtt`) or Word files, so people had to copy
everything into a text file first. Decided 2026-11-03 (Sara): accept `.docx`, `.pdf` and `.vtt`.

Everything downstream works on a version's text and its paragraphs (blocks): citations name a
block, quotes are checked against its text, speakers are found in it (ADR 0012), and approval and
export never look at the file. Uploaded files are untrusted, and these formats are containers
that can hide macros, scripts, links and compressed data that unpacks to far more than was sent.

## Decision

**Convert once, at upload.** A reader turns the file into ordered passages. Each passage becomes
exactly one block of the stored text, joined by blank lines, so `split_into_blocks` gives the same
blocks on every read and citations, approval and export work unchanged. The original filename,
its media type, size and checksum are kept; the original bytes are not stored.

**Where a block came from.** A block keeps the PDF page it is on (`page`), and a transcript block
the time it was said (`start_ms`) and the speaker label it starts with (`speaker`), each null when
the file does not say. The API returns them on every block.

**One reader per format**, behind a `DocumentReader` port, in `sources.infrastructure`:

| Format  | Library     | Passages                                                             |
| ------- | ----------- | -------------------------------------------------------------------- |
| `.docx` | python-docx | Main-document paragraphs and tables in order; a table is one passage |
| `.pdf`  | pypdf       | Each page's paragraphs, from layout extraction, with the page number |
| `.vtt`  | webvtt-py   | Captions with their voice tag and start time, joined into turns      |

A WebVTT transcript is stored as one paragraph per turn ("Mira Holt: ..."), joining a speaker's
consecutive captions up to about 1,000 characters. In a Word transcript, a paragraph that is only
a Teams header ("Mira Holt 0:03") is joined to the turn after it. Both then read like a text
transcript, so speaker detection (ADR 0012) works on them unchanged. Headers, footers, comments,
footnotes and text boxes in Word are left out.

**Untrusted files.** Each reader checks the content really is its format (the zip and content
type of a Word document, the `%PDF-` header, the `WEBVTT` line), runs in-process with no network
access and never runs anything inside the file. A macro-enabled Word file is refused. Before
python-docx opens a Word archive, its declared sizes are checked (at most 1,000 parts and 64 MiB
unpacked); zipfile never reads past a declared size. PDF streams are unpacked under pypdf's own
limits, and a PDF has at most 500 pages. XML entities are never expanded. A WebVTT file whose
captions the library could not all read is refused rather than stored with words missing.

**Refusals.** Each has its own code and a message that names the file and says what to do:

| Refusal                                  | Status | Code                        |
| ---------------------------------------- | ------ | --------------------------- |
| Content is not the type the name says    | 415    | `SOURCE_TYPE_MISMATCH`      |
| Protected by a password                  | 422    | `SOURCE_PASSWORD_PROTECTED` |
| A PDF with no text layer (scanned pages) | 422    | `SOURCE_SCANNED`            |
| Damaged or unreadable                    | 422    | `SOURCE_UNREADABLE`         |
| Unpacks too large, or too many pages     | 422    | `SOURCE_TOO_LARGE_UNPACKED` |

A PDF that only restricts printing or copying, with an empty password to open it, is read.

**Size.** Text files keep `SOURCE_MAX_BYTES` (512 KiB). Word, PDF and WebVTT files have their own
`SOURCE_MAX_DOCUMENT_BYTES` (10 MiB), because images, layout and timings take space beside the
words; the word limit (ADR 0009) is what bounds the text either way. A file over its limit is
still `413 SOURCE_TOO_LARGE`.

## Consequences

- People upload what they have. Evidence shows "page 4" for a PDF quote and the time of a
  transcript quote.
- The stored text is the converted text, not the file. A corrected file is a new version, as
  before; re-reading old uploads with a better converter would need the original files, which are
  not kept.
- One upload of 20 documents at the limit holds up to 200 MiB in memory before it is checked; a
  hosted deployment caps the request body at its proxy, as the sources README already says.
- Conversion runs in the request. A PDF that is slow to read slows that request; a hosted
  deployment with many users should move conversion to a worker with a time limit.
- PDF layout extraction reads columns side by side as one line, and scanned PDFs, PowerPoint,
  Excel, email files and a live Teams or Zoom connection stay out of scope.
- Three libraries (python-docx, pypdf with its `crypto` extra, webvtt-py) are pinned in `uv.lock`
  and need watching for security fixes.
