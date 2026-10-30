import type { ReactNode } from "react";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CHAT_DRAFT_KEY } from "@/lib/chatLaunch";
import { emptyChatDraft } from "@/lib/paperSelection";
import { useChatAutoSend } from "./useChatAutoSend";

const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter>{children}</MemoryRouter>;

function mountChat() {
  const restoreDraft = vi.fn();
  const onPaperSelectionChange = vi.fn();
  renderHook(() => useChatAutoSend({
    pendingDraft: emptyChatDraft(),
    setPendingDraft: vi.fn(),
    blocked: true,
    authLoading: false,
    signedIn: true,
    send: vi.fn(),
    restoreDraft,
    setSelectedModel: vi.fn(),
    onPaperSelectionChange,
  }), { wrapper });
  return { restoreDraft, onPaperSelectionChange };
}

describe("useChatAutoSend", () => {
  afterEach(() => sessionStorage.clear());

  it("restores a kept prompt into one chat surface only, without clearing a reader passage", () => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(emptyChatDraft("Explain the method")));

    const first = mountChat();
    expect(first.restoreDraft).toHaveBeenCalledWith(expect.objectContaining({ text: "Explain the method" }));
    expect(first.onPaperSelectionChange).not.toHaveBeenCalled();

    const later = mountChat();
    expect(later.restoreDraft).not.toHaveBeenCalled();
  });
});
