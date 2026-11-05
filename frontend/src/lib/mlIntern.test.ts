import { describe, expect, it } from "vitest";

import { mlInternReproducePrompt, mlInternReproduceUrl } from "./mlIntern";

describe("mlInternReproducePrompt", () => {
  it("names the paper and its versionless arXiv id", () => {
    const prompt = mlInternReproducePrompt("Attention Is All You Need", "1706.03762v7");
    expect(prompt).toMatch(/^Reproduce the central claims of the research paper "Attention Is All You Need" \(arXiv:1706\.03762\)\. /);
    expect(prompt).toContain("smaller-scale experiments that can still validate or falsify the claims");
    expect(prompt).toContain("README.md at the bucket's root");
  });

  it("omits the arXiv reference for external papers", () => {
    expect(mlInternReproducePrompt("Some Report", null)).toMatch(/^Reproduce the central claims of the research paper "Some Report"\. /);
  });
});

describe("mlInternReproduceUrl", () => {
  it("opens HuggingChat in ML Intern mode with the prompt", () => {
    const url = new URL(mlInternReproduceUrl("Some Report", null));
    expect(url.origin + url.pathname).toBe("https://huggingface.co/chat/");
    expect(url.searchParams.get("mode")).toBe("ml-intern");
    expect(url.searchParams.get("prompt")).toBe(mlInternReproducePrompt("Some Report", null));
  });
});
