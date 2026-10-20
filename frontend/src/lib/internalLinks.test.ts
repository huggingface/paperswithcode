import { describe, expect, it } from "vitest";

import {
  extractPaperRouteId,
  parseHostList,
  resolveInternalPath,
} from "@/lib/internalLinks";

describe("parseHostList", () => {
  it("splits, trims, lowercases and drops empty entries", () => {
    expect(parseHostList(" 203.0.113.10, Example.TEST ,,")).toEqual([
      "203.0.113.10",
      "example.test",
    ]);
    expect(parseHostList(undefined)).toEqual([]);
  });
});

describe("resolveInternalPath", () => {
  it.each([
    ["/paper/2501.12326", "/paper/2501.12326"],
    [
      "https://paperswithcode.co/paper/2501.12326?tab=results#benchmarks",
      "/paper/2501.12326?tab=results#benchmarks",
    ],
    [
      "https://www.paperswithcode.co/papers/104561",
      "/papers/104561",
    ],
    ["/benchmark/imagenet", "/benchmark/imagenet"],
  ])("resolves internal URL %s", (href, expected) => {
    expect(resolveInternalPath(href, "https://paperswithcode.co")).toBe(expected);
  });

  it.each([
    "https://example.com/paper/2501.12326",
    "http://203.0.113.10:8080/paper/2501.12326",
    "https://paperswithcode.co/about",
    "not a URL",
  ])("rejects non-internal URL %s", (href) => {
    expect(resolveInternalPath(href, "https://paperswithcode.co")).toBeNull();
  });
});

describe("extractPaperRouteId", () => {
  it.each([
    ["/paper/2501.12326", "2501.12326"],
    ["/paper/2501-12326", "2501.12326"],
    ["/paper/2501.12326v2", "2501.12326"],
    ["/paper/2501-12326v12?tab=results#leaderboard", "2501.12326"],
    ["/paper/104561", "104561"],
    ["/papers/2501.12326", "2501.12326"],
  ])("extracts %s", (path, expected) => {
    expect(extractPaperRouteId(path)).toBe(expected);
  });

  it.each([
    "/paper",
    "/papers",
    "/paper/",
    "/paper/0",
    "/paper/0012",
    "/paper/not-a-paper",
    "/paper/2501.12326/extra",
    "/paper/2501%2F12326",
    "/paper/2501%2E12326",
    "/paper/%",
    "/tasks/computer-use-agents",
  ])("rejects %s", (path) => {
    expect(extractPaperRouteId(path)).toBeNull();
  });
});
