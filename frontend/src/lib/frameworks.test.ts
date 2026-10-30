import { describe, expect, it } from "vitest";

import { formatStarCount, PLATFORM_LABELS } from "./frameworks";

describe("framework presentation", () => {
  it("defines every supported platform label", () => {
    expect(PLATFORM_LABELS).toEqual({
      gpu: "GPU",
      cpu: "CPU",
      apple: "Apple silicon",
    });
  });

  it("compacts star counts from one thousand", () => {
    expect(formatStarCount(999)).toBe("999");
    expect(formatStarCount(26_414)).toBe("26.4K");
  });
});
