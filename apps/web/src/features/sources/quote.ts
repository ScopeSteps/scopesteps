export interface QuoteParts {
  before: string;
  quote: string;
  after: string;
}

/**
 * Where a quotation sits in its paragraph, or null if it is not there letter for letter. The API
 * accepts quotes that differ from the paragraph in markdown emphasis or whitespace, so a null
 * here means "show the quote next to the paragraph", not "the citation is wrong".
 */
export function locateQuote(text: string, quote: string | null | undefined): QuoteParts | null {
  if (!quote) {
    return null;
  }
  const start = text.indexOf(quote);
  if (start < 0) {
    return null;
  }
  return {
    before: text.slice(0, start),
    quote,
    after: text.slice(start + quote.length),
  };
}
