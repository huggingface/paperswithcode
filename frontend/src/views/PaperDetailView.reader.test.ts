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

  it("does not offer the reader for an external HTML-only resource", () => {
    expect(paperReaderRoute({
      id: "109744",
      arxiv_id: null,
      source: "external",
      source_url: "https://example.com/blog",
    } as Paper, "109744")).toBeNull();
  });
});
