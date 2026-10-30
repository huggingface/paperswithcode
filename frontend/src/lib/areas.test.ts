import { describe, expect, it } from "vitest";

import { sortAreas } from "./areas";

describe("sortAreas", () => {
  it("puts curated areas first and new areas alphabetically after them", () => {
    const names = ["Robotics", "Other", "Language", "Biology", "General", "Vision"];
    expect(sortAreas(names.map((name) => ({ name }))).map((area) => area.name)).toEqual([
      "General",
      "Vision",
      "Language",
      "Other",
      "Biology",
      "Robotics",
    ]);
  });
});
