import { describe, expect, it } from "vitest";

import type { OpenAIUsageStatus } from "@/lib/api/chat.types";
import { openAiCreditsNotice } from "@/lib/openaiCredits";

const usage = (used: number): OpenAIUsageStatus => ({
  used_percent: used,
  remaining_percent: 100 - used,
  resets_at: "2026-10-01T00:00:00Z",
  available: used < 100,
  as_of: "2026-09-19T12:00:00Z",
});

describe("openAiCreditsNotice", () => {
  it("shows the remaining share once 90% of the monthly credits are used", () => {
    const notice = openAiCreditsNotice(usage(94), "openai", null);
    expect(notice?.message).toMatch(/^You have 6% left of your monthly OpenAI credits\. They reset on/);
    expect(notice?.resetsAt).toBe("2026-10-01T00:00:00Z");
  });

  it("stays quiet below the threshold", () => {
    expect(openAiCreditsNotice(usage(89), "openai", null)).toBeNull();
  });

  it("still warns when the credits are fully used", () => {
    expect(openAiCreditsNotice(usage(100), "openai", null)?.message).toMatch(/0% left/);
  });

  it("only applies to the direct OpenAI model", () => {
    expect(openAiCreditsNotice(usage(95), "huggingface", null)).toBeNull();
    expect(openAiCreditsNotice(usage(95), "openrouter", null)).toBeNull();
  });

  it("stays dismissed for the current month and returns after the reset", () => {
    expect(openAiCreditsNotice(usage(95), "openai", "2026-10-01T00:00:00Z")).toBeNull();
    expect(openAiCreditsNotice(usage(95), "openai", "2026-09-01T00:00:00Z")).not.toBeNull();
  });

  it("does nothing without usage data", () => {
    expect(openAiCreditsNotice(undefined, "openai", null)).toBeNull();
  });
});
