import { describe, expect, it, vi } from "vitest";
import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

import { countMatches, createPdfTextIndex } from "./pdfTextIndex";

function fakePdf(pages: string[][]) {
  const getTextContent = vi.fn();
  const getPage = vi.fn(async (pageNumber: number) => ({
    getTextContent: () => {
      getTextContent(pageNumber);
      return Promise.resolve({ items: pages[pageNumber - 1].map((str) => ({ str })) });
    },
  }));
  return { pdf: { numPages: pages.length, getPage } as unknown as PDFDocumentProxy, getPage, getTextContent };
}

describe("createPdfTextIndex", () => {
  it("yields lower-cased page text in order and extracts each page once", async () => {
    const { pdf, getTextContent } = fakePdf([["Attention", "Is"], ["All You"], ["Need"]]);
    const index = createPdfTextIndex(pdf);
    const read = async () => {
      const texts: [number, string][] = [];
      for await (const entry of index.pages()) texts.push(entry);
      return texts;
    };

    expect(await read()).toEqual([[1, "attention is"], [2, "all you"], [3, "need"]]);
    expect(await read()).toHaveLength(3);
    expect(getTextContent).toHaveBeenCalledTimes(3);
  });

  it("retries a page whose text failed to load", async () => {
    const { pdf, getPage } = fakePdf([["Alpha"]]);
    getPage.mockRejectedValueOnce(new Error("range request failed"));
    const index = createPdfTextIndex(pdf);

    await expect(index.pageText(1)).rejects.toThrow("range request failed");
    await expect(index.pageText(1)).resolves.toBe("alpha");
  });
});

it("searches past an unreadable page", async () => {
  const { pdf, getPage } = fakePdf([["Alpha"], ["Beta"], ["Alpha"]]);
  getPage.mockImplementation(async (pageNumber: number) => {
    if (pageNumber === 2) throw new Error("range request failed");
    return { getTextContent: async () => ({ items: [{ str: pageNumber === 1 ? "Alpha" : "Gamma" }] }) };
  });
  const texts: [number, string][] = [];
  for await (const entry of createPdfTextIndex(pdf).pages()) texts.push(entry);

  expect(texts).toEqual([[1, "alpha"], [2, ""], [3, "gamma"]]);
});

describe("countMatches", () => {
  it("counts non-overlapping occurrences", () => {
    expect(countMatches("aaaa", "aa")).toBe(2);
    expect(countMatches("transformer", "former")).toBe(1);
    expect(countMatches("bert", "gpt")).toBe(0);
  });
});
