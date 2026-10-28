import { describe, expect, it } from "vitest";

import { displayTaskName, toSotaRanks } from "./transform";

describe("displayTaskName", () => {
  it("keeps acronyms written in capitals in the task name", () => {
    expect(displayTaskName("PII Detection", "pii-detection")).toBe("PII Detection");
    expect(displayTaskName("LLM Evaluation", "llm-evaluation")).toBe("LLM Evaluation");
  });

  it("title-cases ordinary words", () => {
    expect(displayTaskName("named entity recognition", "named-entity-recognition")).toBe(
      "Named Entity Recognition",
    );
    expect(displayTaskName("egocentric vision", "egocentric-vision")).toBe(
      "Egocentric Vision",
    );
  });

  it("still applies known acronyms and display overrides", () => {
    expect(displayTaskName("3d tracking", "3d-tracking")).toBe("3D Tracking");
    expect(displayTaskName("ocr", "ocr")).toBe("OCR");
    expect(displayTaskName("Text to SQL", "text-to-sql")).toBe("Text-to-SQL");
  });

  it("falls back to the slug when the name is missing", () => {
    expect(displayTaskName(undefined, "robotic-manipulation")).toBe("Robotic Manipulation");
  });
});

describe("toSotaRanks", () => {
  it("links each placement to its highlighted evaluation row", () => {
    expect(
      toSotaRanks([
        { evaluation_id: "42", dataset_name: "ImageNet", dataset_slug: "imagenet", best_rank: 1, task_slug: "image-classification" },
        { evaluation_id: "7", dataset_name: "COCO", dataset_slug: "coco", best_rank: 2, task_slug: null },
        { evaluation_id: "9", dataset_name: "Unlisted", dataset_slug: null, best_rank: 3 },
        { evaluation_id: "8", dataset_name: "Low", dataset_slug: "low", best_rank: 4 },
      ]),
    ).toEqual([
      { name: "ImageNet", href: "/benchmark/imagenet?task=image-classification&eval=42", rank: 1 },
      { name: "COCO", href: "/benchmark/coco?eval=7", rank: 2 },
      { name: "Unlisted", href: null, rank: 3 },
    ]);
  });
});
