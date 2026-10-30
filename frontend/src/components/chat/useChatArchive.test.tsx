import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatArchive } from "./useChatArchive";

const mocks = vi.hoisted(() => ({
  archiveOld: vi.fn(),
  archiveOldest: vi.fn(),
  toast: vi.fn(),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: mocks.toast }),
}));
vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    archiveOldChats: mocks.archiveOld,
    archiveOldestChats: mocks.archiveOldest,
  },
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

describe("useChatArchive", () => {
  beforeEach(() => vi.clearAllMocks());

  it("archives the oldest chats and restores the latest question", async () => {
    mocks.archiveOldest.mockResolvedValue({ archived_count: 2 });
    const refreshSessions = vi.fn().mockResolvedValue(undefined);
    const resetChat = vi.fn();
    const restoreDraft = vi.fn();
    const { result } = renderHook(() => useChatArchive({
      messages: [
        { id: "u1", role: "user", text: "First", paperMentions: [] },
        { id: "u2", role: "user", text: "Latest", paperMentions: [] },
      ],
      refreshSessions,
      resetChat,
      restoreDraft,
    }), { wrapper });

    await act(() => result.current.archiveOldest());

    expect(refreshSessions).toHaveBeenCalledOnce();
    expect(resetChat).toHaveBeenCalledOnce();
    expect(restoreDraft).toHaveBeenCalledWith({ text: "Latest", paperMentions: [] });
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      title: "2 chats archived",
    }));
  });

  it("keeps the current chat when there are no old chats to archive", async () => {
    mocks.archiveOld.mockResolvedValue({ archived_count: 0 });
    const resetChat = vi.fn();
    const { result } = renderHook(() => useChatArchive({
      messages: [],
      refreshSessions: vi.fn().mockResolvedValue(undefined),
      resetChat,
      restoreDraft: vi.fn(),
    }), { wrapper });

    await act(() => result.current.archiveOld());

    expect(resetChat).not.toHaveBeenCalled();
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      title: "No chats were archived",
    }));
  });
});
