import type { PDFDocumentProxy, TextItem } from "pdfjs-dist/types/src/display/api";

// Pages whose text is requested ahead of the one being read, so their byte-range
// fetches and worker extraction overlap instead of running one page at a time.
const READ_AHEAD = 6;

export interface PdfTextIndex {
  /** The page's lower-cased text, extracted once per document. */
  pageText: (pageNumber: number) => Promise<string>;
  /** Yields each page's text in page order, extracting a few pages ahead; unreadable pages yield "". */
  pages: () => AsyncGenerator<[pageNumber: number, text: string]>;
}

export function createPdfTextIndex(pdf: PDFDocumentProxy): PdfTextIndex {
  const texts = new Map<number, Promise<string>>();
  const pageText = (pageNumber: number) => {
    let text = texts.get(pageNumber);
    if (!text) {
      text = pdf.getPage(pageNumber)
        .then((page) => page.getTextContent())
        .then((content) => content.items
          .map((item) => "str" in item ? (item as TextItem).str : "")
          .join(" ")
          .toLocaleLowerCase());
      // A page that failed to load is retried by the next search.
      text.catch(() => texts.delete(pageNumber));
      texts.set(pageNumber, text);
    }
    return text;
  };
  async function* pages(): AsyncGenerator<[number, string]> {
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const last = Math.min(pdf.numPages, pageNumber + READ_AHEAD);
      for (let ahead = pageNumber + 1; ahead <= last; ahead += 1) void pageText(ahead).catch(() => undefined);
      // An unreadable page is searched as empty rather than ending the scan.
      yield [pageNumber, await pageText(pageNumber).catch(() => "")];
    }
  }
  return { pageText, pages };
}

export function countMatches(text: string, query: string): number {
  let count = 0;
  for (let offset = text.indexOf(query); offset >= 0; offset = text.indexOf(query, offset + query.length)) count += 1;
  return count;
}
