import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ComponentProps } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import { chatApi } from "@/lib/api/chat";
import type { ChatMessage as ChatMessageType } from "@/lib/chat";

afterEach(() => {
  delete (document as Partial<Document>).caretPositionFromPoint;
  delete (document as Partial<Document>).caretRangeFromPoint;
  document.getSelection()?.removeAllRanges();
});

describe("UserMessage", () => {
  it("keeps historical paper mentions linked when new mentions are disabled", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><UserMessage
        text="Compare @Attention Is All You Need today"
        paperMentions={[{
          key: "mention-1",
          route_id: "1706.03762",
          title: "Attention Is All You Need",
          source: "arxiv",
          start: 8,
          end: 34,
        }]}
        paperMentionsEnabled={false}
        /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("link", { name: "Attention Is All You Need" }))
      .toHaveAttribute("href", "/paper/1706.03762");
    expect(screen.getByText(/Compare/)).toHaveTextContent("Compare Attention Is All You Need today");
  });

  it("links URLs the user typed without swallowing sentence punctuation", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><UserMessage
          text={"Similar to https://deepmind.google/blog/genie-4/? See (https://en.wikipedia.org/wiki/Genie_(model)) and @Attention Is All You Need."}
          paperMentions={[{
            key: "mention-1",
            route_id: "1706.03762",
            title: "Attention Is All You Need",
            source: "arxiv",
            start: 104,
            end: 130,
          }]}
        /></MemoryRouter>
      </QueryClientProvider>,
    );

    const genie = screen.getByRole("link", { name: "https://deepmind.google/blog/genie-4/" });
    expect(genie).toHaveAttribute("href", "https://deepmind.google/blog/genie-4/");
    expect(genie).toHaveAttribute("target", "_blank");
    expect(genie).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "https://en.wikipedia.org/wiki/Genie_(model)" }))
      .toHaveAttribute("href", "https://en.wikipedia.org/wiki/Genie_(model)");
    expect(screen.getByRole("link", { name: "Attention Is All You Need" }))
      .toHaveAttribute("href", "/paper/1706.03762");
  });

  it("renders a historical selection card without a remove control", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><UserMessage
          text="What does this mean?"
          paperSelection={{
            routeId: "2608.09119",
            paperVersion: "v1",
            page: 4,
            text: "quoted evidence",
          }}
        /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Selection · Page 4")).toBeInTheDocument();
    expect(screen.getByText("quoted evidence")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove selected paper passage" })).not.toBeInTheDocument();
  });

  it("renders new paper-title markers without a visible at-sign", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><UserMessage
        text="Compare Attention Is All You Need today"
        paperMentions={[{
          key: "mention-1",
          route_id: "1706.03762",
          title: "Attention Is All You Need",
          source: "arxiv",
          start: 8,
          end: 33,
        }]}
        /></MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("link", { name: "Attention Is All You Need" }))
      .toHaveAttribute("href", "/paper/1706.03762");
    expect(screen.getByText(/Compare/)).toHaveTextContent("Compare Attention Is All You Need today");
  });

  it("leaves pointer selection to the browser", () => {
    render(<UserMessage text="Select any part of this prompt" />);
    const message = screen.getByText("Select any part of this prompt");

    const firstPressAllowed = fireEvent.mouseDown(message, { button: 0, detail: 1 });
    const secondPressAllowed = fireEvent.mouseDown(message, { button: 0, detail: 2 });

    expect(firstPressAllowed).toBe(true);
    expect(secondPressAllowed).toBe(true);
  });

  it("selects the double-clicked word without cancelling the native event", () => {
    render(<UserMessage text="What's good tiny image classifier" />);
    const message = screen.getByText("What's good tiny image classifier");
    const textNode = message.firstChild;
    expect(textNode).toBeInstanceOf(Text);
    Object.defineProperty(document, "caretRangeFromPoint", {
      configurable: true,
      value: () => {
        const range = document.createRange();
        range.setStart(textNode!, 8);
        range.collapse(true);
        return range;
      },
    });

    const allowed = fireEvent.doubleClick(message, { clientX: 20, clientY: 10 });

    expect(allowed).toBe(true);
    expect(document.getSelection()?.toString()).toBe("good");
  });

  it("copies the full message and confirms success", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<UserMessage text={"Copy this prompt\nincluding its second line"} />);

    await user.click(screen.getByRole("button", { name: "Copy message" }));

    expect(writeText).toHaveBeenCalledWith("Copy this prompt\nincluding its second line");
    expect(screen.getByRole("button", { name: "Message copied" })).toHaveAttribute("title", "Copied");
  });

  it("exposes keyboard-accessible copy and edit actions", async () => {
    const user = userEvent.setup();
    let edited = false;
    render(
      <UserMessage
        id="user-1"
        text="Editable prompt"
        editingAllowed
        onEdit={() => { edited = true; }}
      />,
    );

    const copy = screen.getByRole("button", { name: "Copy message" });
    const edit = screen.getByRole("button", { name: "Edit message" });
    expect(edit).toHaveAttribute("title", "Edit");
    await user.tab();
    expect(copy).toHaveFocus();
    await user.tab();
    expect(edit).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(edited).toBe(true);
  });

  it("focuses the inline editor at the end and resends unchanged text with Enter", async () => {
    const user = userEvent.setup();
    const submissions: string[] = [];
    render(
      <UserMessage
        id="user-1"
        text="Same prompt"
        editing
        editNotice="Sending will replace the response."
        onResend={(text) => { submissions.push(text); return true; }}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "Edit message" });
    expect(editor).toHaveFocus();
    expect(editor).toHaveValue("Same prompt");
    expect((editor as HTMLTextAreaElement).selectionStart).toBe("Same prompt".length);
    expect((editor as HTMLTextAreaElement).selectionEnd).toBe("Same prompt".length);
    expect(screen.getByText("Sending will replace the response.")).toBeVisible();
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Cancel",
      "Send",
    ]);

    await user.keyboard("{Enter}");
    expect(submissions).toEqual(["Same prompt"]);
  });

  it("supports Shift+Enter for newlines and Escape to cancel", async () => {
    const user = userEvent.setup();
    let cancelled = false;
    const submissions: string[] = [];
    render(
      <UserMessage
        text="Line one"
        editing
        onCancel={() => { cancelled = true; }}
        onResend={(text) => { submissions.push(text); return true; }}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "Edit message" });

    await user.keyboard("{Shift>}{Enter}{/Shift}Line two");
    expect(editor).toHaveValue("Line one\nLine two");
    expect(submissions).toEqual([]);
    await user.keyboard("{Escape}");
    expect(cancelled).toBe(true);
  });

  it("keeps selected papers highlighted inline while editing", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <UserMessage
        text="Compare Deep Paper"
        paperMentions={[{
          key: "mention-1",
          route_id: "2501.00001",
          title: "Deep Paper",
          source: "arxiv",
          start: 8,
          end: 18,
        }]}
        paperMentionsEnabled
        editing
        onResendDraft={() => true}
      />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("combobox", { name: "Edit message" }))
      .toHaveValue("Compare Deep Paper");
    expect(container.querySelector(".chat-paper-inline-highlight"))
      .toHaveTextContent("Deep Paper");
    expect(container.querySelector(".chat-paper-chips")).not.toBeInTheDocument();
  });

  it("rejects whitespace-only edits", async () => {
    const user = userEvent.setup();
    render(<UserMessage text="Original" editing onResend={() => true} />);
    const editor = screen.getByRole("textbox", { name: "Edit message" });
    await user.clear(editor);
    await user.type(editor, "   ");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("AssistantMessage", () => {
  const renderAssistant = (
    msg: ChatMessageType,
    hfBilling: ComponentProps<typeof AssistantMessage>["hfBilling"] = null,
    openRouterFallbackEnabled = false,
  ) => render(
    <AssistantMessage
      msg={msg}
      papers={{}}
      onToggleBlock={() => undefined}
      hfBilling={hfBilling}
      openRouterFallbackEnabled={openRouterFallbackEnabled}
    />,
  );

  it("renders a scope refusal as a normal completed response", () => {
    renderAssistant({
      id: "assistant-scope-blocked",
      role: "assistant",
      finishReason: "scope_blocked",
      blocks: [{ kind: "answer", text: "Research-only refusal", done: true }],
    });

    expect(screen.getByText("Research-only refusal")).toBeVisible();
    expect(screen.queryByText(/stopped early/i)).not.toBeInTheDocument();
  });

  it("renders completed reasoning as Markdown", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      blocks: [{
        kind: "reasoning",
        text: "**Researching object detection**\n\n- Check benchmarks\n- Read papers",
        active: false,
        open: true,
      }],
    });

    expect(screen.getByText("Researching object detection").tagName).toBe("STRONG");
    expect(screen.getByRole("list")).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("routes external paper snapshots to the scholarly preview renderer", () => {
    const url = "https://arxiv.org/abs/2608.01234";
    renderAssistant({
      id: "assistant-external-paper",
      role: "assistant",
      citations: [{
        kind: "external_source",
        route_id: null,
        url,
        source_type: "paper",
        provider: "semantic_scholar",
        title: "A Brand New Paper",
        source_url: "https://www.semanticscholar.org/paper/s2-id",
      }],
      blocks: [{
        kind: "answer",
        text: `[A Brand New Paper](${url})`,
        done: true,
      }],
    });

    expect(screen.getByRole("link", { name: "A Brand New Paper" }))
      .toHaveClass("chat-external-paper-citation");
  });

  it("submits thumbs feedback for a completed answer", async () => {
    const user = userEvent.setup();
    const reportFeedback = vi.spyOn(chatApi, "reportFeedback").mockResolvedValue();
    render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          blocks: [{ kind: "answer", text: "A useful answer", done: true }],
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        feedbackEnabled
      />,
    );

    await user.click(screen.getByRole("button", { name: "Helpful response" }));

    expect(reportFeedback).toHaveBeenCalledWith("assistant-1", true);
    expect(screen.getByText("Thanks for your feedback")).toBeVisible();
    expect(screen.getByRole("button", { name: "Helpful response" })).toHaveAttribute("aria-pressed", "true");
  });

  it("collects an optional comment before submitting thumbs down", async () => {
    const user = userEvent.setup();
    const reportFeedback = vi.spyOn(chatApi, "reportFeedback").mockResolvedValue();
    render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          blocks: [{ kind: "answer", text: "A very long answer", done: true }],
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        feedbackEnabled
      />,
    );

    await user.click(screen.getByRole("button", { name: "Unhelpful response" }));

    expect(reportFeedback).not.toHaveBeenCalled();
    const comment = screen.getByLabelText("Tell us what went wrong (optional)");
    expect(comment).toHaveFocus();
    await user.type(comment, "The answer is too long.");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(reportFeedback).toHaveBeenCalledWith(
      "assistant-1",
      false,
      "The answer is too long.",
    );
    expect(screen.getByText("Thanks for your feedback")).toBeVisible();
    expect(screen.queryByText("Additional feedback")).not.toBeInTheDocument();
  });

  it("submits thumbs down without a comment when skipped", async () => {
    const user = userEvent.setup();
    const reportFeedback = vi.spyOn(chatApi, "reportFeedback").mockResolvedValue();
    render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          blocks: [{ kind: "answer", text: "An answer", done: true }],
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        feedbackEnabled
      />,
    );

    await user.click(screen.getByRole("button", { name: "Unhelpful response" }));
    await user.click(screen.getByRole("button", { name: "Skip" }));

    expect(reportFeedback).toHaveBeenCalledWith("assistant-1", false);
  });

  it("hides feedback while streaming and in public views", () => {
    const { rerender } = render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          streaming: true,
          blocks: [{ kind: "answer", text: "Partial", done: false }],
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        feedbackEnabled
      />,
    );
    expect(screen.queryByLabelText("Rate this response")).not.toBeInTheDocument();

    rerender(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          blocks: [{ kind: "answer", text: "Complete", done: true }],
        }}
        papers={{}}
        onToggleBlock={() => undefined}
      />,
    );
    expect(screen.queryByLabelText("Rate this response")).not.toBeInTheDocument();
  });

  it("offers PRO only for an exhausted personal Free account", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Review pay-as-you-go billing.",
      errorCode: "hf_inference_billing_exhausted",
    }, {
      account_type: "Free",
      bill_to: null,
      usage_url: "https://huggingface.co/settings/inference-providers",
    });

    expect(screen.getByText(/Review pay-as-you-go billing/)).toBeVisible();
    expect(screen.getByRole("link", { name: /Upgrade to Hugging Face PRO/ })).toHaveAttribute(
      "href",
      "https://huggingface.co/pro",
    );
    expect(screen.getByRole("link", { name: /pricing and billing details/i })).toHaveAttribute(
      "href",
      "https://huggingface.co/docs/inference-providers/pricing",
    );
  });

  it.each([
    { account_type: "PRO" as const, bill_to: null },
    { account_type: "Organization" as const, bill_to: "huggingface" },
  ])("directs $account_type billing exhaustion to account usage", (target) => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Included usage is exhausted.",
      errorCode: "hf_inference_billing_exhausted",
    }, {
      ...target,
      usage_url: "https://huggingface.co/settings/inference-providers",
    });

    expect(screen.queryByRole("link", { name: /Upgrade to Hugging Face PRO/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review Hugging Face usage and billing" })).toHaveAttribute(
      "href",
      "https://huggingface.co/settings/inference-providers",
    );
  });

  it("offers an explicit Luna retry for exhausted HF billing", () => {
    const onRetryWithLuna = vi.fn();
    const msg: ChatMessageType = {
      id: "assistant-1",
      role: "assistant",
      error: "Included usage is exhausted.",
      errorCode: "hf_inference_billing_exhausted",
    };
    const { rerender } = render(
      <AssistantMessage msg={msg} papers={{}} onToggleBlock={() => undefined} onRetryWithLuna={onRetryWithLuna} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry with GPT-6 Luna" }));
    expect(onRetryWithLuna).toHaveBeenCalledTimes(1);

    rerender(<AssistantMessage msg={msg} papers={{}} onToggleBlock={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Retry with GPT-6 Luna" })).not.toBeInTheDocument();
  });

  it("links a missing HF token directly to Settings", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Your Hugging Face Inference Providers authorization is missing or expired. Re-sign in with Hugging Face to continue.",
      errorCode: "hf_inference_billing_required",
    });

    expect(screen.getByRole("link", { name: "Re-sign in with Hugging Face" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("explains an insufficient shared reservation and offers explicit alternatives", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "40% of your monthly shared OpenRouter allowance remains, but that is not enough to reserve another model call for this response. It resets at 2026-09-01T00:00:00Z.",
      errorCode: "openrouter_monthly_budget_exhausted",
    });

    expect(screen.getByText(/40%.*remains.*not enough to reserve/i)).toBeVisible();
    expect(screen.getByText(/resets at 2026-09-01T00:00:00Z/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Connect your own OpenRouter key" })).toHaveAttribute(
      "href",
      "/settings#openrouter-byok",
    );
    expect(screen.getByText(/select a Hugging Face-backed model and explicitly retry/)).toBeVisible();
    expect(screen.queryByText(/capacity|provider rate/i)).not.toBeInTheDocument();
  });

  it("explains that an enabled OpenRouter fallback applies on explicit retry", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "The remaining shared Papers With Code OpenRouter allowance is not enough for another model call.",
      errorCode: "openrouter_monthly_budget_exhausted",
    }, null, true);

    expect(screen.getByText(/response started on the shared allowance/i)).toBeVisible();
    expect(screen.getByText(/connected OpenRouter key will be used when you explicitly retry/i)).toBeVisible();
    expect(screen.queryByRole("link", { name: /OpenRouter key/i })).not.toBeInTheDocument();
  });

  it("redirects users when shared staging funding has ended", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Shared staging credits have ended because chat is now live on paperswithcode.co.",
      errorCode: "openrouter_staging_funding_disabled",
    });

    expect(screen.getByRole("link", { name: "Continue on paperswithcode.co" })).toHaveAttribute(
      "href",
      "https://paperswithcode.co/chat",
    );
    expect(screen.queryByRole("link", { name: /own OpenRouter key/i })).not.toBeInTheDocument();
  });

  it("uses the generic OpenRouter-unavailable contract without pool details", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "OpenRouter is currently unavailable. However, you can still bring your own key in Settings.",
      errorCode: "openrouter_unavailable",
    });

    expect(screen.getByRole("link", { name: "Bring your own key in Settings" })).toHaveAttribute(
      "href",
      "/settings#openrouter-byok",
    );
    expect(screen.getByRole("link", { name: "File an issue" })).toHaveAttribute(
      "href",
      "https://github.com/huggingface/paperswithcode-feedback",
    );
    expect(screen.queryByText(/shared|workspace|pool|spend|headroom/i)).not.toBeInTheDocument();
  });

  it("explains that a BYOK spending limit is not an account balance", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      error: "Your OpenRouter key is connected, but OpenRouter rejected billing for the account behind it. A key spending limit is not an account credit balance. Add credits or enable pay-as-you-go in OpenRouter, then try again.",
      errorCode: "openrouter_byok_billing_error",
    });

    expect(screen.getByText(/spending limit is not an account credit balance/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Review OpenRouter billing" })).toHaveAttribute(
      "href",
      "https://openrouter.ai/settings/credits",
    );
    expect(screen.queryByRole("link", { name: "Review OpenRouter settings" })).not.toBeInTheDocument();
  });

  it("explains the chat limit and offers bulk archiving", async () => {
    const onArchive = vi.fn();
    const onArchiveOldest = vi.fn();
    const user = userEvent.setup();
    render(
      <AssistantMessage
        msg={{
          id: "assistant-1",
          role: "assistant",
          error: "You can have at most 100 chats. Archive old chats or delete a chat to create another.",
          errorCode: "chat_session_quota_exceeded",
        }}
        papers={{}}
        onToggleBlock={() => undefined}
        onArchiveOldChats={onArchive}
        onArchiveOldestChats={onArchiveOldest}
      />,
    );

    expect(screen.getByText(/at most 100 chats/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Archive chats older than 30 days" }));
    expect(onArchive).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Archive oldest 50 chats" }));
    expect(onArchiveOldest).toHaveBeenCalledOnce();
  });

  it("shows a thinking status while waiting for the first streamed block", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [],
    });

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
    expect(screen.getByText("Thinking…")).toHaveClass("chat-thinking");
  });

  it("renders the delayed workspace status accessibly", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      status: "Preparing research workspace…",
      blocks: [],
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing research workspace…",
    );
  });

  it("does not reuse the workspace status after streamed work has started", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      status: "Preparing research workspace…",
      blocks: [{
        kind: "reasoning",
        text: "Checked the evidence.",
        active: false,
        open: false,
      }],
    });

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
    expect(screen.queryByText("Preparing research workspace…")).not.toBeInTheDocument();
  });

  it.each([
    {
      name: "completed reasoning",
      block: { kind: "reasoning", text: "Checked the evidence.", active: false, open: false } as const,
    },
    {
      name: "completed tool call",
      block: {
        kind: "tool",
        id: "tool-1",
        name: "search_papers",
        args: {},
        status: "success",
        open: false,
      } as const,
    },
  ])("shows thinking after a $name while waiting for the next step", ({ block }) => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [block],
    });

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
  });

  it.each([
    {
      name: "active reasoning",
      block: { kind: "reasoning", text: "Still checking.", active: true, open: true } as const,
    },
    {
      name: "running tool call",
      block: {
        kind: "tool",
        id: "tool-1",
        name: "search_papers",
        args: {},
        status: "running",
        open: false,
      } as const,
    },
    {
      name: "streaming answer",
      block: { kind: "answer", text: "The result is", done: false } as const,
    },
  ])("does not add a waiting status during $name", ({ block }) => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [block],
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a caret only on the active tail answer block", () => {
    const { container } = renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [
        { kind: "answer", text: "First answer segment.", done: false },
        {
          kind: "tool",
          id: "tool-1",
          name: "Bash",
          args: { command: "pwc benchmark list" },
          status: "done",
          hits: 0,
          took_ms: 10,
          results: [],
          open: false,
        },
        { kind: "answer", text: "Latest answer segment.", done: false },
      ],
    });

    expect(container.querySelectorAll(".chat-caret")).toHaveLength(1);
  });

  it("does not show an answer caret while a tool is running", () => {
    const { container } = renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [
        { kind: "answer", text: "I will check the benchmark.", done: false },
        {
          kind: "tool",
          id: "tool-1",
          name: "Bash",
          args: { command: "pwc benchmark list" },
          status: "running",
          open: false,
        },
      ],
    });

    expect(container.querySelectorAll(".chat-caret")).toHaveLength(0);
  });

  it.each([
    ["pwc_get_task", { task: "object-detection" }, "task=object-detection"],
    ["pwc_get_benchmark", { benchmark: "coco-val2017", limit: 15, is_open: null }, "benchmark=coco-val2017 · limit=15"],
    ["pwc_get_paper_info", { paper: "2511.09554" }, "paper=2511.09554"],
    ["pwc_search_papers", { query: "real-time object detection", has_official_implementation: false, page: 0, published_after: "" }, "query=real-time object detection · has_official_implementation=false · page=0"],
  ])("shows %s arguments while the tool card is collapsed", (name, args, summary) => {
    renderAssistant({
      id: "assistant-1", role: "assistant", streaming: false,
      blocks: [{
        kind: "tool", schema_version: 2, id: "tool-1", name, args,
        status: "success", open: false, took_ms: 195,
      }],
    });
    const bar = screen.getByRole("button", { name: new RegExp(name) });
    expect(bar).toHaveAttribute("aria-expanded", "false");
    expect(bar).toHaveTextContent(summary);
    expect(screen.getByTitle(summary)).toBeInTheDocument();
    expect(screen.queryByText("arguments")).not.toBeInTheDocument();
  });

  it("shows progressive safe arguments while a tool is still running", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: true,
      blocks: [{
        kind: "tool",
        schema_version: 2,
        id: "tool-1",
        name: "Bash",
        args: { command: "pwc benchmark" },
        argumentText: '{"command":"pwc benchmark',
        argumentState: "streaming",
        arguments_redacted: true,
        status: "running",
        open: true,
      }],
    });

    expect(screen.getByText("streaming arguments…")).toBeInTheDocument();
    expect(screen.getByText("arguments · redacted")).toBeInTheDocument();
    expect(screen.getAllByText("pwc benchmark").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Bash/u })).not.toBeDisabled();
  });

  it("renders an Excalidraw App placeholder and keeps the textual answer", () => {
    renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: false,
      blocks: [
        {
          kind: "app",
          schema_version: 1,
          instance_id: "app-1",
          provider: "excalidraw",
          server: "excalidraw",
          tool: "create_view",
          resource_uri: "ui://excalidraw/mcp-app.html",
          status: "loading",
          input: { elements: "[]" },
          result: { content: [], structuredContent: {}, isError: false },
          csp: {},
          permissions: { clipboardWrite: true },
          height: 525,
        },
        { kind: "answer", text: "This schematic compares the two methods.", done: true },
      ],
    });

    expect(screen.getByRole("region", { name: "Interactive Excalidraw diagram" })).toBeVisible();
    expect(screen.queryByText("Visual explanation")).not.toBeInTheDocument();
    expect(screen.queryByText(/Experimental/)).not.toBeInTheDocument();
    expect(screen.queryByText(/processed by the remote Excalidraw MCP service/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry diagram" })).toBeVisible();
    expect(screen.getByText("This schematic compares the two methods.")).toBeVisible();
  });

  it("exits an Excalidraw diagram fullscreen overlay on Escape", async () => {
    const user = userEvent.setup();
    const { container } = renderAssistant({
      id: "assistant-1",
      role: "assistant",
      streaming: false,
      blocks: [
        {
          kind: "app",
          schema_version: 1,
          instance_id: "app-1",
          provider: "excalidraw",
          server: "excalidraw",
          tool: "create_view",
          resource_uri: "ui://excalidraw/mcp-app.html",
          status: "loading",
          input: { elements: "[]" },
          result: { content: [], structuredContent: {}, isError: false },
          csp: {},
          permissions: { clipboardWrite: true },
          height: 525,
        },
      ],
    });

    await user.click(screen.getByRole("button", { name: "Fullscreen" }));
    expect(container.querySelector(".chat-mcp-app-fullscreen")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Exit fullscreen" })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(container.querySelector(".chat-mcp-app-fullscreen")).toBeNull();
    expect(screen.getByRole("button", { name: "Fullscreen" })).toBeVisible();
  });
});

it("marks a partial failed response incomplete and offers recovery", () => {
  const retry = vi.fn();
  render(<MemoryRouter><AssistantMessage
    msg={{ id: "partial", role: "assistant", error: "Recovery timed out", errorCode: "context_too_large",
      blocks: [{ kind: "answer", text: "Useful partial findings", done: true }] }}
    papers={{}} onToggleBlock={() => {}} onRetryCompaction={retry}
  /></MemoryRouter>);
  expect(screen.getByText("Useful partial findings")).toBeVisible();
  expect(screen.getByText(/Incomplete—response interrupted/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalledOnce();
});
