import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CompactionStatus } from "./CompactionStatus";
import { AssistantMessage } from "./ChatMessage";

afterEach(() => { cleanup(); vi.useRealTimers(); });

it("explains the delay after 15 seconds and cancels its timer on removal", () => {
  vi.useFakeTimers();
  const view = render(<CompactionStatus />);
  expect(screen.getByRole("status")).toHaveTextContent("Summarizing earlier context…");
  expect(screen.queryByText(/This conversation is long/)).toBeNull();
  act(() => vi.advanceTimersByTime(15_000));
  expect(screen.getByText(/This conversation is long/)).toBeVisible();
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it("keeps answer text visible, replaces the waiting status, and disappears on completion", () => {
  const props = { papers: {}, onToggleBlock: vi.fn() };
  const message = { id: "a", role: "assistant" as const, streaming: true, compacting: true,
    blocks: [{ kind: "answer" as const, text: "Existing answer", done: false }] };
  const view = render(<AssistantMessage {...props} msg={message} />);
  expect(screen.getByText("Existing answer")).toBeVisible();
  expect(screen.getAllByRole("status")).toHaveLength(1);
  view.rerender(<AssistantMessage {...props} msg={{ ...message, streaming: false }} />);
  expect(screen.queryByText("Summarizing earlier context…")).toBeNull();
});

it("offers an explicit retry only for recoverable context failures", () => {
  const retry = vi.fn();
  render(<AssistantMessage papers={{}} onToggleBlock={vi.fn()} onRetryCompaction={retry}
    msg={{ id: "a", role: "assistant", error: "Your conversation is saved.", errorCode: "context_too_large" }} />);
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalledOnce();
});
