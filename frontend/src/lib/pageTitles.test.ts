import { describe, expect, it } from "vitest";

import { benchmarkPageTitle, entityPageTitle, taskPageTitle } from "@/lib/pageTitles";

describe("page titles mirror the server-injected titles", () => {
  it("formats entity, task and benchmark titles", () => {
    expect(entityPageTitle("Google")).toBe("Google — papers and benchmarks | Papers with Code");
    expect(taskPageTitle("Image Classification", false)).toBe(
      "Image Classification — papers and benchmarks | Papers with Code",
    );
    expect(taskPageTitle("Image Classification", true, new Date(2026, 10, 18))).toBe(
      "Best Image Classification Models (November 2026): leaderboards and papers | Papers with Code",
    );
    expect(benchmarkPageTitle("ImageNet")).toBe(
      "ImageNet Leaderboard: state of the art results | Papers with Code",
    );
  });
});
