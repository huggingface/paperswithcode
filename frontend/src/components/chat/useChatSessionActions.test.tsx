import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useChatSessionActions } from "./useChatSessionActions";
import { chatApi } from "@/lib/api/chat";

const renderActions = (overrides: Partial<Parameters<typeof useChatSessionActions>[0]> = {}) => {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const options = {
    routeSessionId: "b",
    selectedModel: "luna",
    setSelectedModel: vi.fn(),
    patchSession: vi.fn(),
    onRenamed: vi.fn(),
    refreshSessions: vi.fn(async () => undefined),
    onError: vi.fn(),
    onSelectedDeleted: vi.fn(),
    isActive: () => false,
    stopActive: vi.fn(),
    ...overrides,
  };
  return { options, ...renderHook(() => useChatSessionActions(options), { wrapper }) };
};

describe("useChatSessionActions removeMany", () => {
  afterEach(() => vi.restoreAllMocks());

  it("deletes every chat after one confirmation and leaves the open chat once", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const removeSession = vi.spyOn(chatApi, "removeSession").mockResolvedValue(undefined);
    const { result, options } = renderActions();

    let deleted = false;
    await act(async () => { deleted = await result.current.removeMany(["a", "b", "c"]); });

    expect(deleted).toBe(true);
    expect(confirm).toHaveBeenCalledOnce();
    expect(confirm).toHaveBeenCalledWith("Delete these 3 chats? This cannot be undone.");
    expect(removeSession.mock.calls.map(([id]) => id)).toEqual(["a", "b", "c"]);
    expect(options.onSelectedDeleted).toHaveBeenCalledOnce();
    expect(options.refreshSessions).toHaveBeenCalledOnce();
  });

  it("stops at the first failure and reports it", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const removeSession = vi.spyOn(chatApi, "removeSession")
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("boom"));
    const { result, options } = renderActions({ routeSessionId: undefined });

    let deleted = true;
    await act(async () => { deleted = await result.current.removeMany(["a", "b", "c"]); });

    expect(deleted).toBe(false);
    expect(removeSession).toHaveBeenCalledTimes(2);
    expect(options.onError).toHaveBeenCalledWith("boom");
    expect(options.refreshSessions).toHaveBeenCalledOnce();
  });
});
