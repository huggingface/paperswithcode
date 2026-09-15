import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "@/lib/chat";
import { ChatConversation } from "./ChatConversation";

vi.mock("./ChatMessage", () => ({
  UserMessage: ({ id, onResendDraft }: {
    id: string;
    onResendDraft: (draft: { text: string; paperMentions: [] }) => boolean;
  }) => <div data-message-id={id}>
    <button onClick={() => onResendDraft({ text: "Edited question", paperMentions: [] })}>Edit {id}</button>
  </div>,
  AssistantMessage: ({ onToggleBlock, onRetryCompaction, msg }: {
    onToggleBlock: (id: string, index: number) => void;
    msg: ChatMessage;
    onRetryCompaction?: () => void;
  }) => <div><button onClick={() => onToggleBlock(msg.id, 0)}>Toggle reasoning</button>
    {onRetryCompaction && <button onClick={onRetryCompaction}>Retry</button>}
  </div>,
}));

afterEach(() => vi.restoreAllMocks());

function setup(editAccepted = true) {
  let height = 1000;
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(() => height);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
  // JSDOM has no layout; emulate the browser's clamped scroll position.
  const positions = new WeakMap<HTMLElement, number>();
  vi.spyOn(HTMLElement.prototype, "scrollTop", "get")
    .mockImplementation(function (this: HTMLElement) { return positions.get(this) ?? 0; });
  vi.spyOn(HTMLElement.prototype, "scrollTop", "set")
    .mockImplementation(function (this: HTMLElement, value: number) {
      positions.set(this, Math.max(0, Math.min(value, height - 400)));
    });
  let messages: ChatMessage[] = [
    { id: "question", role: "user", text: "Question" },
    { id: "answer", role: "assistant", streaming: true },
  ];
  const props = {
    papers: {}, busy: true, paperMentionsEnabled: false, archivePending: null,
    openRouterFallbackEnabled: false, onToggleBlock: vi.fn(),
    onEditAndResend: vi.fn().mockReturnValue(editAccepted), onArchiveOld: vi.fn(), onArchiveOldest: vi.fn(),
  };
  const view = render(<ChatConversation {...props} messages={messages} />);
  const scroller = view.container.querySelector<HTMLDivElement>(".chat-conversation")!;
  return {
    ...view, scroller,
    scrollTo(top: number) {
      scroller.scrollTop = top;
      fireEvent.scroll(scroller);
    },
    update(nextMessages = messages, busy = true) {
      height += 200;
      messages = [...nextMessages];
      view.rerender(<ChatConversation {...props} busy={busy} messages={messages} />);
    },
  };
}

describe("ChatConversation scrolling", () => {
  it("opens at the bottom and follows streamed content", () => {
    const chat = setup();
    expect(chat.scroller.scrollTop).toBe(600);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(800);
  });
  it("preserves the reader's position through streaming and completion", () => {
    const chat = setup();
    chat.scrollTo(200);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(200);
    chat.update([{ id: "question", role: "user" }, { id: "answer", role: "assistant", streaming: false }], false);
    expect(chat.scroller.scrollTop).toBe(200);
  });
  it("resumes following only when the reader requests the latest response", () => {
    const chat = setup();
    chat.scrollTo(200);
    chat.update();
    chat.scrollTo(780);
    expect(chat.getByRole("button", { name: "Jump to latest" })).toBeTruthy();
    fireEvent.click(chat.getByRole("button", { name: "Jump to latest" }));
    expect(document.activeElement).toBe(chat.scroller);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(1000);
  });
  it("preserves even a small upward scroll during streaming", () => {
    const chat = setup();
    chat.scrollTo(595);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(595);
  });
  it("pauses on upward wheel intent before a scroll event arrives", () => {
    const chat = setup();
    fireEvent.wheel(chat.scroller, { deltaY: -1 });
    // A queued programmatic scroll event at the bottom must not resume following.
    fireEvent.scroll(chat.scroller);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(600);
  });
  it("pauses on upward touch intent", () => {
    const chat = setup();
    fireEvent.touchStart(chat.scroller, { touches: [{ clientY: 100 }] });
    fireEvent.touchMove(chat.scroller, { touches: [{ clientY: 105 }] });
    chat.update();
    expect(chat.scroller.scrollTop).toBe(600);
  });
  it("pauses on keyboard navigation toward earlier messages", () => {
    const chat = setup();
    fireEvent.keyDown(chat.scroller, { key: "PageUp" });
    chat.update();
    expect(chat.scroller.scrollTop).toBe(600);
  });
  it("follows a newly submitted question even after scrolling up", () => {
    const chat = setup();
    chat.scrollTo(200);
    chat.update([
      { id: "question", role: "user" },
      { id: "answer", role: "assistant" },
      { id: "next-question", role: "user", text: "Next question" },
    ]);
    expect(chat.scroller.scrollTop).toBe(800);
  });
  it("preserves position when toggling reasoning and on subsequent updates", () => {
    const chat = setup();
    chat.scrollTo(200);
    fireEvent.click(chat.getByText("Toggle reasoning"));
    chat.update();
    expect(chat.scroller.scrollTop).toBe(200);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(200);
  });
  it("anchors an edited follow-up once, then lets the reader scroll freely", () => {
    const chat = setup();
    const messages: ChatMessage[] = [
      { id: "question", role: "user" },
      { id: "follow-up", role: "user" },
    ];
    chat.update(messages, false);
    fireEvent.click(chat.getByText("Edit follow-up"));
    chat.update(messages);
    expect(chat.scroller.scrollTop).toBe(776);
    chat.scrollTo(200);
    chat.update(messages);
    expect(chat.scroller.scrollTop).toBe(200);
  });
  it("preserves position when completion replaces optimistic IDs with canonical IDs", () => {
    const chat = setup();
    chat.scrollTo(200);
    chat.update([
      { id: "saved-question", role: "user", text: "Question", revision: 1 },
      { id: "saved-answer", role: "assistant", streaming: false },
    ]);
    expect(chat.scroller.scrollTop).toBe(200);
    chat.update(undefined, false);
    expect(chat.scroller.scrollTop).toBe(200);
  });
  it("follows an accepted first-question edit even though its ID stays the same", () => {
    const chat = setup();
    chat.update(undefined, false);
    chat.scrollTo(200);
    fireEvent.click(chat.getByText("Edit question"));
    chat.update([
      { id: "question", role: "user", text: "Edited question", revision: 2 },
      { id: "replacement-answer", role: "assistant", streaming: true },
    ]);
    expect(chat.scroller.scrollTop).toBe(1000);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(1200);
  });
  it("does not resume following when a first-question edit is rejected", () => {
    const chat = setup(false);
    chat.update(undefined, false);
    chat.scrollTo(200);
    fireEvent.click(chat.getByText("Edit question"));
    chat.update(undefined, false);
    expect(chat.scroller.scrollTop).toBe(200);
  });
  it("restores following when a composer retry starts with the same user count", () => {
    const chat = setup();
    chat.update(undefined, false);
    chat.scrollTo(200);
    chat.update([
      { id: "question", role: "user", text: "Retry question", revision: 2 },
      { id: "retry-answer", role: "assistant", streaming: true },
    ]);
    expect(chat.scroller.scrollTop).toBe(1000);
    chat.scrollTo(200);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(200);
  });
});


it("continues only the latest persisted turn without rewinding research", () => {
  const onEditAndResend = vi.fn(() => true);
  const onRetryFromProgress = vi.fn(() => true);
  const props = {
    papers: {}, busy: false, paperMentionsEnabled: false, archivePending: null,
    openRouterFallbackEnabled: false, onToggleBlock: vi.fn(), onEditAndResend, onRetryFromProgress,
    onArchiveOld: vi.fn(), onArchiveOldest: vi.fn(),
  };
  const user: ChatMessage = { id: "q", role: "user", text: "Keep the citations", paperMentions: [] };
  const assistant: ChatMessage = { id: "a", role: "assistant", errorCode: "context_too_large" };
  const view = render(<ChatConversation {...props} messages={[user, assistant]} />);
  expect(view.queryByText("Retry")).toBeNull();
  view.rerender(<ChatConversation {...props} messages={[{ ...user, revision: 1 }, assistant]} />);
  fireEvent.click(view.getByText("Retry"));
  expect(onRetryFromProgress).toHaveBeenCalledOnce();
  expect(onEditAndResend).not.toHaveBeenCalled();
  view.rerender(<ChatConversation {...props} busy messages={[{ ...user, revision: 1 }, assistant]} />);
  expect(view.queryByText("Retry")).toBeNull();
});
