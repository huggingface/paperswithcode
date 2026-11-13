import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRenderThrottledText } from "@/components/chat/useRenderThrottledText";

describe("useRenderThrottledText", () => {
  it("passes text straight through when not throttling", () => {
    const { result, rerender } = renderHook(
      ({ text }) => useRenderThrottledText(text, false),
      { initialProps: { text: "a" } },
    );
    rerender({ text: "ab" });
    expect(result.current).toBe("ab");
  });

  it("catches up with the latest streamed text", async () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRenderThrottledText(text, streaming),
      { initialProps: { text: "a", streaming: true } },
    );
    rerender({ text: "ab", streaming: true });
    rerender({ text: "abc", streaming: true });
    await waitFor(() => expect(result.current).toBe("abc"));
  });

  it("shows the full text as soon as streaming ends", () => {
    const { result, rerender } = renderHook(
      ({ text, streaming }) => useRenderThrottledText(text, streaming),
      { initialProps: { text: "a", streaming: true } },
    );
    rerender({ text: "final", streaming: false });
    expect(result.current).toBe("final");
  });
});
