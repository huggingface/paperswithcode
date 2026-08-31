import { describe, expect, it } from "vitest";

import {
  readHomepagePaperDateRange,
  withHomepagePaperDateRange,
} from "@/lib/paperDateRange";

describe("homepage paper date range", () => {
  it("defaults a bare homepage to the last seven UTC dates", () => {
    expect(readHomepagePaperDateRange(
      new URLSearchParams(),
      new Date("2026-08-21T23:30:00Z"),
    )).toEqual({
      startDate: "2026-08-15",
      endDate: "2026-08-21",
    });
  });

  it("preserves explicit date ranges", () => {
    const params = new URLSearchParams("start_date=2026-08-01&end_date=2026-08-03");

    expect(readHomepagePaperDateRange(params)).toEqual({
      startDate: "2026-08-01",
      endDate: "2026-08-03",
    });
  });

  it("keeps all time as an explicit homepage choice", () => {
    const params = withHomepagePaperDateRange(
      new URLSearchParams("order_by=trending"),
      {},
    );

    expect(params.get("time")).toBe("all_time");
    expect(params.get("order_by")).toBe("trending");
    expect(readHomepagePaperDateRange(params)).toEqual({});
  });
});
