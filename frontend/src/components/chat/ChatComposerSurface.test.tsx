import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { ChatComposerSurface } from "./ChatComposerSurface";

const message = "Paper context is still being prepared. The PDF remains available; please retry chat later.";

function renderSurface(variant: "empty" | "followup", error?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    <ChatComposerSurface
      variant={variant}
      composerProps={{ draft: { text: "What is GitSwarm?", paperMentions: [] }, onDraftChange: () => {}, onSend: () => {} }}
      provider="openai"
      paused={false}
      error={error}
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
});
