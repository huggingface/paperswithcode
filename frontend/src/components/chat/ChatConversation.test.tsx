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
  AssistantMessage: ({ onToggleBlock, msg }: {
    onToggleBlock: (id: string, index: number) => void;
    msg: ChatMessage;
  }) => <button onClick={() => onToggleBlock(msg.id, 0)}>Toggle reasoning</button>,
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
  it("resumes following when the reader scrolls back near the bottom", () => {
    const chat = setup();
    chat.scrollTo(200);
    chat.update();
    chat.scrollTo(780);
    chat.update();
    expect(chat.scroller.scrollTop).toBe(1000);
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
