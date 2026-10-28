import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Composer from "./Composer";
import type { Paper } from "@/lib/api/papers.types";
import { chatApi } from "@/lib/api/chat";
import { papersApi } from "@/lib/api/papers";
import type { ChatDraft } from "@/lib/chat";

const paper: Paper = {
  id: "42", arxiv_id: "2501.00001", source: "arxiv", source_url: null,
  url_abs: "https://arxiv.org/abs/2501.00001", url_pdf: null,
  title: "Deep Paper", abstract: "", authors: [], published: "2026-01-01",
  version: "v1", is_latest_version: true, citation_count: 0,
};
const secondPaper: Paper = { ...paper, id: "43", arxiv_id: "2502.00002", title: "Ovis" };

function Harness({ onSend }: { onSend: (draft: ChatDraft) => void }) {
  const [draft, setDraft] = React.useState<ChatDraft>({ text: "", paperMentions: [] });
  return <Composer draft={draft} onDraftChange={setDraft} onSend={onSend} paperMentionsEnabled />;
}

describe("Composer paper mentions", () => {
  beforeEach(() => {
    vi.spyOn(papersApi, "search").mockResolvedValue({ next_page: null, previous_page: null, results: [paper] });
    vi.spyOn(chatApi, "prewarmPaperContext").mockResolvedValue(undefined);
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("debounces hybrid search, lets Enter attach before sending, and prewarms once", async () => {
    const onSend = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(<QueryClientProvider client={client}><Harness onSend={onSend} /></QueryClientProvider>);
    const textarea = screen.getByRole("combobox");
    fireEvent.change(textarea, { target: { value: "@d", selectionStart: 2 } });
    expect(papersApi.search).not.toHaveBeenCalled();
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    expect(papersApi.search).toHaveBeenCalledWith("d", 1, 10, "hybrid", expect.any(AbortSignal));
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("Deep Paper ");
    await waitFor(() => expect((textarea as HTMLTextAreaElement).selectionStart).toBe(11));
    expect(container.querySelector(".chat-paper-inline-highlight")).toHaveTextContent("Deep Paper");
    expect(screen.queryByLabelText("Attached papers")).not.toBeInTheDocument();
    expect(chatApi.prewarmPaperContext).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith(expect.objectContaining({
      text: "Deep Paper",
      paperMentions: [expect.objectContaining({ route_id: "2501.00001", start: 0, end: 10 })],
    }));
  });

  it("uses an existing following space and moves the caret past it when a result is clicked", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><Harness onSend={vi.fn()} /></QueryClientProvider>);
    const textarea = screen.getByRole("combobox");
    fireEvent.change(textarea, { target: { value: "Compare @d later", selectionStart: 10 } });
    const option = await screen.findByRole("option", { name: /Deep Paper/ });

    fireEvent.mouseDown(option);

    expect(textarea).toHaveValue("Compare Deep Paper later");
    await waitFor(() => expect((textarea as HTMLTextAreaElement).selectionStart).toBe(19));
  });

  it("highlights multiple selected papers in place inside a sentence", async () => {
    vi.mocked(papersApi.search).mockImplementation(async (query) => ({
      next_page: null,
      previous_page: null,
      results: query === "ovi" ? [secondPaper] : [paper],
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}><Harness onSend={vi.fn()} /></QueryClientProvider>,
    );
    const textarea = screen.getByRole("combobox");

    fireEvent.change(textarea, { target: { value: "How does @dee", selectionStart: 13 } });
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(textarea).toHaveValue("How does Deep Paper "));
    fireEvent.change(textarea, {
      target: { value: "How does Deep Paper compare to @ovi", selectionStart: 35 },
    });
    (textarea as HTMLTextAreaElement).setSelectionRange(35, 35);
    fireEvent.select(textarea);
    expect(await screen.findByRole("option", { name: /Ovis/ })).toBeInTheDocument();
    fireEvent.keyDown(textarea, { key: "Enter" });
    fireEvent.change(textarea, {
      target: { value: "How does Deep Paper compare to Ovis?", selectionStart: 36 },
    });

    expect(textarea).toHaveValue("How does Deep Paper compare to Ovis?");
    expect([...container.querySelectorAll(".chat-paper-inline-highlight")].map((node) => node.textContent))
      .toEqual(["Deep Paper", "Ovis"]);
    expect(screen.queryByLabelText("Attached papers")).not.toBeInTheDocument();
  });
});

describe("Composer paper commands", () => {
  it("marks the private chat draft surface as excluded from analytics capture", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <Composer onSend={vi.fn()} />
      </QueryClientProvider>,
    );

    const surface = container.querySelector(".chat-composer");
    const textarea = screen.getByRole("combobox");
    expect(surface).toHaveClass("ph-no-capture");
    expect(surface).toHaveAttribute("data-ph-no-capture", "true");
    expect(surface).toHaveAttribute("data-ph-no-autocapture", "true");
    expect(textarea).toHaveClass("ph-no-capture");
    expect(textarea).toHaveAttribute("data-ph-no-capture", "true");
    expect(textarea).toHaveAttribute("data-ph-no-autocapture", "true");
  });

  it("suggests /write-paper only when paper artifacts are enabled and slash is typed", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <Composer onSend={vi.fn()} paperArtifactsEnabled />
      </QueryClientProvider>,
    );
    const textarea = screen.getByRole("combobox");
    fireEvent.change(textarea, { target: { value: "/", selectionStart: 1 } });
    expect(screen.getByRole("option", { name: /write-paper/i })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("option", { name: /write-paper/i }));
    expect(textarea).toHaveValue("/write-paper ");

    rerender(
      <QueryClientProvider client={client}>
        <Composer onSend={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("option", { name: /write-paper/i })).not.toBeInTheDocument();
  });
});

describe("Composer paper selection", () => {
  it("renders the card above an empty composer and does not send without a question", () => {
    const onSend = vi.fn();
    const onDraftChange = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Composer
          draft={{
            text: "",
            paperMentions: [],
            paperSelection: {
              routeId: "2608.09119",
              paperVersion: "v1",
              page: 4,
              text: "quoted evidence",
            },
          }}
          onDraftChange={onDraftChange}
          onSend={onSend}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Selection · Page 4")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask about this selection…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Remove selected paper passage" }));
    expect(onDraftChange).toHaveBeenCalledWith({ text: "", paperMentions: [] });
    expect(onSend).not.toHaveBeenCalled();
  });
});
