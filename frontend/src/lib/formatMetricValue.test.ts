import { describe, expect, it } from "vitest";

import { formatMetricValue } from "@/lib/utils";

describe("formatMetricValue", () => {
  it("rounds decimal ties away from zero regardless of binary representation", () => {
    expect(formatMetricValue(30.55)).toBe("30.6");
    expect(formatMetricValue(22.95)).toBe("23.0");
    expect(formatMetricValue(38.55)).toBe("38.6");
    expect(formatMetricValue("1.005")).toBe("1.01");
    expect(formatMetricValue(0.0005)).toBe("0.001");
    expect(formatMetricValue(-22.95)).toBe("-23.0");
  });

  it("keeps magnitude-based precision and placeholders", () => {
    expect(formatMetricValue(100.5)).toBe("101");
    expect(formatMetricValue(0.1234)).toBe("0.123");
    expect(formatMetricValue(1e-7)).toBe("0.000");
    expect(formatMetricValue(null)).toBe("—");
    expect(formatMetricValue("n/a")).toBe("n/a");
  });
});
