import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { ChatComposerSurface } from "./ChatComposerSurface";

const message = "Paper context is still being prepared. The PDF remains available; please retry chat later.";

function renderSurface(variant: "empty" | "followup", error?: string, suggestionLinks?: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    <ChatComposerSurface
      variant={variant}
      composerProps={{ draft: { text: "What is GitSwarm?", paperMentions: [] }, onDraftChange: () => {}, onSend: () => {} }}
      provider="openai"
      paused={false}
      error={error}
      suggestions={["Explain in simple terms"]}
      suggestionLinks={suggestionLinks}
    />
  </QueryClientProvider>);
}

describe("ChatComposerSurface", () => {
  it.each(["empty", "followup"] as const)("shows a rejected send's reason beside the %s composer", (variant) => {
    const { unmount } = renderSurface(variant, message);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert.compareDocumentPosition(screen.getByRole("combobox")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    unmount();
  });

  it("renders no alert without an error", () => {
    renderSurface("empty");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows suggestion links beside the suggestions only in the empty state", () => {
    const link = <a href="https://huggingface.co/chat/">Reproduce with ML Intern</a>;
    const { unmount } = renderSurface("empty", undefined, link);
    expect(screen.getByRole("link", { name: "Reproduce with ML Intern" }).parentElement)
      .toBe(screen.getByRole("button", { name: "Explain in simple terms" }).parentElement);
    unmount();
    renderSurface("followup", undefined, link);
    expect(screen.queryByRole("link", { name: "Reproduce with ML Intern" })).not.toBeInTheDocument();
  });
});

describe("ChatComposerSurface suggestions with uploads", () => {
  const file = { id: "file-1", filename: "notes.pdf", media_type: "application/pdf", size_bytes: 4 };
  const renderWithFiles = (onSend: (draft: unknown) => void, uploading = false) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}>
      <ChatComposerSurface
        variant="empty"
        composerProps={{
          draft: { text: "typed", paperMentions: [], files: [file], fileSessionId: "session-1" },
          onDraftChange: () => {},
          onSend,
        }}
        provider="openai"
        paused={false}
        uploading={uploading}
        suggestions={["Explain in simple terms"]}
      />
    </QueryClientProvider>);
  };

  it("sends a suggestion with the attached files", () => {
    const sent: unknown[] = [];
    renderWithFiles((draft) => sent.push(draft));
    fireEvent.click(screen.getByRole("button", { name: "Explain in simple terms" }));
    expect(sent).toEqual([{
      text: "Explain in simple terms", paperMentions: [], files: [file], fileSessionId: "session-1",
    }]);
  });

  it("disables suggestions while files upload", () => {
    renderWithFiles(() => {}, true);
    expect(screen.getByRole("button", { name: "Explain in simple terms" })).toBeDisabled();
  });
});
