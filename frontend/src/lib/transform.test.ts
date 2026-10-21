import { describe, expect, it } from "vitest";

import { displayTaskName } from "./transform";

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
