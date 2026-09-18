import { describe, expect, it } from "vitest";
import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

import { activeSectionIndex, loadPdfOutline, pdfSectionFromHash } from "./pdfOutline";

const pageRef = (page: number) => ({ num: page * 10, gen: 0 });

function fakePdf(outline: unknown[] | null) {
  return {
    numPages: 12,
    getOutline: async () => outline,
    getDestination: async (name: string) => name === "section.2" ? [pageRef(3), { name: "XYZ" }, 72, 396, null] : null,
    getPageIndex: async (ref: { num: number }) => ref.num / 10 - 1,
    getPage: async () => ({ view: [0, 0, 612, 792] }),
  } as unknown as PDFDocumentProxy;
}

describe("loadPdfOutline", () => {
  it("flattens bookmarks in document order with resolved page positions", async () => {
    const entries = await loadPdfOutline(fakePdf([
      { title: "Introduction", dest: [pageRef(1), { name: "XYZ" }, 72, 720, null], items: [] },
      {
        title: "System  Design\n",
        dest: "section.2",
        items: [
          { title: "SSD Streaming", dest: [pageRef(4), { name: "Fit" }], items: [
            { title: "Too deep", dest: [pageRef(4), { name: "Fit" }], items: [] },
          ] },
          { title: "Dangling", dest: "missing", items: [] },
        ],
      },
      { title: "Appendix", dest: [pageRef(99), { name: "Fit" }], items: [] },
    ]));
    expect(entries).toEqual([
      { index: 0, title: "Introduction", level: 0, page: 1, offset: (792 - 720) / 792 },
      { index: 1, title: "System Design", level: 0, page: 3, offset: 0.5 },
      { index: 2, title: "SSD Streaming", level: 1, page: 4, offset: 0 },
    ]);
  });

  it("yields no sections for documents without bookmarks", async () => {
    expect(await loadPdfOutline(fakePdf(null))).toEqual([]);
    expect(await loadPdfOutline(fakePdf([]))).toEqual([]);
  });
});

describe("activeSectionIndex", () => {
  it("marks the last section starting at or above the reading anchor", () => {
    expect(activeSectionIndex([-900, -100, 24, 800], 24)).toBe(2);
    expect(activeSectionIndex([-900, -100, 25, 800], 24)).toBe(1);
    expect(activeSectionIndex([-900, Number.POSITIVE_INFINITY, 800], 24)).toBe(0);
  });
  it("marks nothing before the first section", () => {
    expect(activeSectionIndex([200, 900], 24)).toBe(-1);
    expect(activeSectionIndex([], 24)).toBe(-1);
  });
});

describe("pdfSectionFromHash", () => {
  it("reads alphaXiv-style section anchors only", () => {
    expect(pdfSectionFromHash("#pdf-section-5")).toBe(5);
    expect(pdfSectionFromHash("#pdf-section-0")).toBe(0);
    expect(pdfSectionFromHash("#page=3")).toBeUndefined();
    expect(pdfSectionFromHash("")).toBeUndefined();
  });
});
