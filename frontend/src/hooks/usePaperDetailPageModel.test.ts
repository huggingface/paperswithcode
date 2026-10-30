import { beforeEach, describe, expect, it, vi } from "vitest";

const { primeEvaluations, primePaper } = vi.hoisted(() => ({
  primeEvaluations: vi.fn().mockResolvedValue(undefined),
  primePaper: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/api/evaluations", () => ({
  evaluationsApi: { primeCurationState: primeEvaluations },
}));
vi.mock("@/lib/api/papers", () => ({
  papersApi: { primeCurationState: primePaper },
}));

import {
  parsePaperSectionHash,
  refreshAfterCatalogConflict,
  resultsTaskAnchorId,
  resultsTaskHash,
} from "./usePaperDetailPageModel";

beforeEach(() => {
  primeEvaluations.mockClear();
  primePaper.mockClear();
});

describe("paper detail page model", () => {
  it("parses section and task-specific result hashes", () => {
    expect(parsePaperSectionHash("abstract")).toEqual({
      section: "abstract",
      resultsTaskSlug: null,
    });
    expect(parsePaperSectionHash("results?task=visual%2Bquestion-answering")).toEqual({
      section: "results",
      resultsTaskSlug: "visual+question-answering",
    });
    expect(parsePaperSectionHash("unknown")).toEqual({
      section: null,
      resultsTaskSlug: null,
    });
    expect(resultsTaskAnchorId("image-classification")).toBe(
      "results-task-image-classification",
    );
    expect(resultsTaskHash("visual qa")).toBe("#results?task=visual%20qa");
  });

  it("refreshes visible data and primes direct-edit conflict state", () => {
    const refetchPaper = vi.fn();
    const refetchEvaluations = vi.fn();

    refreshAfterCatalogConflict({
      direct: true,
      paperId: "17",
      refetchEvaluations,
      refetchPaper,
    });

    expect(refetchPaper).toHaveBeenCalledOnce();
    expect(refetchEvaluations).toHaveBeenCalledOnce();
    expect(primePaper).toHaveBeenCalledWith("17", true);
    expect(primeEvaluations).toHaveBeenCalledWith("17", true);
  });

  it("does not prime pending-edit conflict state", () => {
    refreshAfterCatalogConflict({
      direct: false,
      paperId: "17",
      refetchEvaluations: vi.fn(),
      refetchPaper: vi.fn(),
    });

    expect(primePaper).not.toHaveBeenCalled();
    expect(primeEvaluations).not.toHaveBeenCalled();
  });
});
