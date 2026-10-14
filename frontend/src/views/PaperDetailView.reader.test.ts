import { describe, expect, it } from "vitest";

import type { Paper } from "@/lib/api/papers.types";
import { paperReaderRoute } from "@/lib/paperReader";

describe("paper detail reader action", () => {
  it("routes a PDF-like external source through the catalog paper ID", () => {
    expect(paperReaderRoute({
      id: "109743",
      arxiv_id: null,
      source: "external",
      source_url: "https://github.com/acme/report/blob/main/report.pdf",
      conference_url_pdf: "https://example.com/conference-copy.pdf",
    } as Paper, "109743")).toBe("/pdf/109743");
  });

  it("routes an external web page through the catalog paper ID", () => {
    expect(paperReaderRoute({
      id: "109744",
      arxiv_id: null,
      source: "external",
      source_url: "https://example.com/blog",
    } as Paper, "109744")).toBe("/pdf/109744");
  });

  it.each([
    "https://doi.org/10.1145/3763359",
    "https://aclanthology.org/2020.lrec-1.297/",
    "https://www.sciencedirect.com/science/article/pii/1",
    "https://ras.papercept.net/program.html#thi1i_171",
  ])("does not offer the reader for the landing or listing page %s", (sourceUrl) => {
    expect(paperReaderRoute({
      id: "109745",
      arxiv_id: null,
      source: "external",
      source_url: sourceUrl,
    } as Paper, "109745")).toBeNull();
  });
});
