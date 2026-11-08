import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { paperDatePresetRange } from "@/lib/paperDateRange";

const renderParams = (entry: string, options?: Parameters<typeof usePaperFeedParams>[0]) => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[entry]}>{children}</MemoryRouter>
  );
  return renderHook(() => ({ feed: usePaperFeedParams(options), search: useLocation().search }), { wrapper });
};

describe("usePaperFeedParams", () => {
  it("reads sort, resource toggles and dates from the URL", () => {
    const { result } = renderParams(
      "/x?order_by=citation_count&has_code=true&start_date=2026-01-01&end_date=2026-02-01",
    );
    expect(result.current.feed.filters).toEqual({
      order_by: "citation_count",
      order_dir: "desc",
      latest_only: true,
      include_resources: true,
      has_code: true,
      has_hf_artifacts: false,
      start_date: "2026-01-01",
      end_date: "2026-02-01",
    });
  });

  it("treats explicit and unknown sorts as trending", () => {
    expect(renderParams("/x?order_by=trending").result.current.feed.orderBy).toBe("trending");
    expect(renderParams("/x?order_by=bogus").result.current.feed.orderBy).toBe("trending");
  });

  it("writes non-default values and drops the default sort", () => {
    const { result } = renderParams("/x?framework=lerobot");
    act(() => result.current.feed.setOrderBy("date_published"));
    expect(result.current.search).toBe("?framework=lerobot&order_by=date_published");
    act(() => result.current.feed.setHasHfArtifacts(true));
    act(() => result.current.feed.setOrderBy("trending"));
    expect(result.current.search).toBe("?framework=lerobot&has_hf_artifacts=true");
  });

  it("defaults to all time unless asked for the last month", () => {
    expect(renderParams("/x").result.current.feed.dateRange).toEqual({});
    const { result } = renderParams("/x", { defaultToLastMonth: true });
    expect(result.current.feed.dateRange).toEqual(paperDatePresetRange("month", new Date(new Date().toISOString().slice(0, 10))));
    act(() => result.current.feed.setDateRange({}));
    expect(result.current.search).toBe("?time=all_time");
    expect(result.current.feed.dateRange).toEqual({});
  });
});
