import { describe, expect, it } from "vitest";

import { spliceDictation } from "@/components/chat/useComposerDictation";
import type { ChatDraft } from "@/lib/chat";

const draft = (text: string, paperMentions: ChatDraft["paperMentions"] = []): ChatDraft => ({ text, paperMentions });

describe("spliceDictation", () => {
  it("drops the provider's leading space in an empty draft", () => {
    const next = spliceDictation({ draft: draft(""), start: 0, end: 0 }, " He hoped");
    expect(next.draft.text).toBe("He hoped");
    expect(next.caret).toBe(8);
  });

  it("adds a space after existing text and before following text", () => {
    const next = spliceDictation({ draft: draft("Compare with"), start: 7, end: 7 }, " LoRA");
    expect(next.draft.text).toBe("Compare LoRA with");
    expect(next.caret).toBe("Compare LoRA".length);
  });

  it("does not pad before punctuation", () => {
    const next = spliceDictation({ draft: draft("Explain ."), start: 8, end: 8 }, "attention");
    expect(next.draft.text).toBe("Explain attention.");
  });

  it("replaces the selection captured at the start", () => {
    const next = spliceDictation({ draft: draft("Explain ResNet please"), start: 8, end: 14 }, " Mamba");
    expect(next.draft.text).toBe("Explain Mamba please");
  });

  it("keeps paper mentions anchored around the inserted text", () => {
    const mention = { key: "k", route_id: "1706.03762", title: "Attention", source: "arxiv" as const, start: 10, end: 19 };
    const next = spliceDictation({ draft: draft("Summarize Attention", [mention]), start: 0, end: 0 }, " Please");
    expect(next.draft.text).toBe("Please Summarize Attention");
    expect(next.draft.paperMentions).toEqual([{ ...mention, start: 17, end: 26 }]);
  });

  it("leaves the draft unchanged before any text arrives", () => {
    const original = draft("Keep me");
    expect(spliceDictation({ draft: original, start: 7, end: 7 }, "").draft.text).toBe("Keep me");
  });
});
