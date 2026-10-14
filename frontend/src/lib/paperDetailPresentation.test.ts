import { describe, expect, it } from "vitest";

import type { Paper } from "./api/papers.types";
import { buildPaperDetailPresentation } from "./paperDetailPresentation";

const paper: Paper = {
  id: "17",
  arxiv_id: "2608.00123v2",
  url_abs: "https://arxiv.org/abs/2608.00123",
  url_pdf: "https://arxiv.org/pdf/2608.00123",
  title: "A sufficiently descriptive paper title",
  abstract: "Abstract",
  authors: ["Ada Lovelace", "Grace Hopper"],
  published: "2026-08-01",
  version: "v2",
  is_latest_version: true,
  citation_count: 3,
  hf_models: ["https://huggingface.co/org/model"],
  hf_datasets: [],
  hf_spaces: [],
};

describe("paper detail presentation model", () => {
  it("deduplicates explicit and discovered artifacts and derives stable labels", () => {
    const model = buildPaperDetailPresentation(paper, {
      models: 2,
      datasets: 0,
      spaces: 0,
      modelUrls: [
        "https://huggingface.co/org/model",
        "https://huggingface.co/org/second-model",
      ],
      datasetUrls: [],
      spaceUrls: [],
      isLimited: false,
      paperExists: true,
    }, false);

    expect(model.allHfArtifactUrls.models).toEqual([
      "https://huggingface.co/org/model",
      "https://huggingface.co/org/second-model",
    ]);
    expect(model.hfArtifactViewer.rows[0].count).toBe(2);
    expect(model.hfArtifactViewer.rows[0].links?.map(({ label }) => label)).toEqual([
      "model",
      "second model",
    ]);
    expect(model.paperSourceLabel).toBe("arXiv:2608.00123v2");
    expect(model.citationCopy).toContain("Ada Lovelace and Grace Hopper");
  });

  it("carries each linked author's Hugging Face avatar", () => {
    const model = buildPaperDetailPresentation(
      {
        ...paper,
        author_links: [
          { id: "1", name: "Ada Lovelace", hf_username: "ada", hf_avatar_url: "/avatars/ada.svg" },
          { id: "2", name: "Grace Hopper", hf_username: null, hf_avatar_url: null },
        ],
      },
      undefined,
      false,
    );

    expect(model.authorEntries.map(({ hf_avatar_url }) => hf_avatar_url)).toEqual([
      "/avatars/ada.svg",
      null,
    ]);
  });
});
