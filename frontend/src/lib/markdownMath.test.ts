import { describe, expect, it } from "vitest";

import { mightContainMath } from "./markdownMath";

describe("mightContainMath", () => {
  it("detects dollar and backslash math delimiters", () => {
    expect(mightContainMath("Loss is $x^2$.")).toBe(true);
    expect(mightContainMath("$$\\sum_i x_i$$")).toBe(true);
    expect(mightContainMath("Inline \\(a+b\\) math")).toBe(true);
    expect(mightContainMath("Display \\[a+b\\] math")).toBe(true);
  });

  it("skips KaTeX for plain Markdown", () => {
    expect(mightContainMath("A **bold** [link](/tasks/x) with (parentheses).")).toBe(false);
  });
});
