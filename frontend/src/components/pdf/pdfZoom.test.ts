import { describe, expect, it } from "vitest";

import { clampZoom, MAX_ZOOM, MIN_ZOOM, stepZoom } from "./pdfZoom";

describe("pdfZoom", () => {
  it("steps from any zoom to the neighbouring preset", () => {
    expect(stepZoom(1, 1)).toBe(1.1);
    expect(stepZoom(1, -1)).toBe(0.9);
    expect(stepZoom(1.37, 1)).toBe(1.5);
    expect(stepZoom(1.37, -1)).toBe(1.25);
    expect(stepZoom(MAX_ZOOM, 1)).toBe(MAX_ZOOM);
    expect(stepZoom(MIN_ZOOM, -1)).toBe(MIN_ZOOM);
  });

  it("clamps continuous zoom to the supported range", () => {
    expect(clampZoom(0.1)).toBe(MIN_ZOOM);
    expect(clampZoom(1.234)).toBe(1.234);
    expect(clampZoom(9)).toBe(MAX_ZOOM);
  });
});
