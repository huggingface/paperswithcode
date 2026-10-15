import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Paper } from "@/lib/api/papers.types";
import { PaperSuggestedQuestions } from "./PaperSuggestedQuestions";

const mocks = vi.hoisted(() => ({ suggestedQuestions: vi.fn(), chatEnabled: vi.fn() }));
vi.mock("@/lib/api/papers", () => ({ papersApi: { suggestedQuestions: mocks.suggestedQuestions } }));
vi.mock("@/lib/apiUrl", () => ({ isChatEnabled: mocks.chatEnabled }));

const paper = {
  id: "42",
  arxiv_id: "2501.00001v2",
  title: "Pooling Autoencoders",
  abstract: "An abstract.",
  suggested_questions: [] as string[],
} as Paper;

function renderQuestions(readerChatRoute: string | null, overrides: Partial<Paper> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PaperSuggestedQuestions paper={{ ...paper, ...overrides }} readerChatRoute={readerChatRoute} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.chatEnabled.mockReturnValue(true);
  mocks.suggestedQuestions.mockResolvedValue({ questions: ["How does pooling work?", "Why DINO?", "Limits?"] });
});

describe("PaperSuggestedQuestions", () => {
  it("asks the reader chat when the paper has one", async () => {
    renderQuestions("/pdf/2501.00001");

    const link = await screen.findByRole("link", { name: "How does pooling work?" });
    expect(link.getAttribute("href")).toBe("/pdf/2501.00001?q=How%20does%20pooling%20work%3F");
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(mocks.suggestedQuestions).toHaveBeenCalledWith("42");
  });

  it("names the paper when falling back to the general chat", async () => {
    renderQuestions(null);

    const link = await screen.findByRole("link", { name: "Why DINO?" });
    const prompt = new URL(link.getAttribute("href")!, "https://x").searchParams.get("q");
    expect(prompt).toBe('About the paper "Pooling Autoencoders" (arXiv:2501.00001): Why DINO?');
  });

  it("renders stored questions from the paper without another request", () => {
    renderQuestions("/pdf/2501.00001", { suggested_questions: ["Stored one?", "Stored two?", "Stored three?"] });

    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Stored one?",
      "Stored two?",
      "Stored three?",
    ]);
    expect(mocks.suggestedQuestions).not.toHaveBeenCalled();
  });

  it("waits for the detail response before generating", () => {
    renderQuestions(null, { suggested_questions: undefined });

    expect(screen.queryByRole("list")).toBeNull();
    expect(mocks.suggestedQuestions).not.toHaveBeenCalled();
  });

  it("stays hidden without chat", () => {
    mocks.chatEnabled.mockReturnValue(false);
    renderQuestions(null);

    expect(screen.queryByRole("list")).toBeNull();
    expect(mocks.suggestedQuestions).not.toHaveBeenCalled();
  });
});
