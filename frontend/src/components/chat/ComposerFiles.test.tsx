import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Composer, { type ComposerFileUploads } from "./Composer";
import { chatApi } from "@/lib/api/chat";
import type { ChatDraft } from "@/lib/chat";
import { draftRequestFields } from "@/lib/chatRequest";

const uploaded = { id: "file-1", filename: "notes.pdf", media_type: "application/pdf", size_bytes: 2048, page_count: 3 };

function Harness({ onSend, fileUploads }: { onSend: (draft: ChatDraft) => void; fileUploads?: ComposerFileUploads }) {
  const [draft, setDraft] = React.useState<ChatDraft>({ text: "", paperMentions: [] });
  const client = React.useMemo(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }), []);
  return (
    <QueryClientProvider client={client}>
      <Composer draft={draft} onDraftChange={setDraft} onSend={onSend} fileUploads={fileUploads} />
    </QueryClientProvider>
  );
}

describe("Composer file attachments", () => {
  beforeEach(() => {
    vi.spyOn(chatApi, "getAutocompleteVocabulary").mockResolvedValue({ names: [] });
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it("has no attach button unless the surface accepts uploads", () => {
    render(<Harness onSend={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Attach files" })).not.toBeInTheDocument();
  });

  it("uploads, shows a removable chip, and sends the file with its chat", async () => {
    const onSend = vi.fn();
    const fileUploads: ComposerFileUploads = {
      upload: vi.fn().mockResolvedValue({ sessionId: "session-1", file: uploaded }),
      remove: vi.fn(),
    };
    const { container } = render(<Harness onSend={onSend} fileUploads={fileUploads} />);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["%PDF-1.7"], "notes.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText("notes.pdf")).toBeInTheDocument();
    expect(screen.getByText("2 KB")).toBeInTheDocument();
    expect(fileUploads.upload).toHaveBeenCalledWith(file, undefined);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Summarize it" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    const draft = onSend.mock.calls[0][0] as ChatDraft;
    expect(draft).toMatchObject({ text: "Summarize it", files: [uploaded], fileSessionId: "session-1" });
    expect(draftRequestFields({}, draft).file_ids).toEqual(["file-1"]);
  });

  it("removes a chip and its uploaded file", async () => {
    const fileUploads: ComposerFileUploads = {
      upload: vi.fn().mockResolvedValue({ sessionId: "session-1", file: uploaded }),
      remove: vi.fn(),
    };
    const { container } = render(<Harness onSend={vi.fn()} fileUploads={fileUploads} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["x"], "notes.pdf")] },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Remove notes.pdf" }));

    await waitFor(() => expect(screen.queryByText("notes.pdf")).not.toBeInTheDocument());
    expect(fileUploads.remove).toHaveBeenCalledWith("session-1", "file-1");
  });

  it("shows the upload error and keeps the draft sendable", async () => {
    const fileUploads: ComposerFileUploads = {
      upload: vi.fn().mockRejectedValue(new Error("boom")),
      remove: vi.fn(),
    };
    const { container } = render(<Harness onSend={vi.fn()} fileUploads={fileUploads} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["x"], "big.pdf")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("big.pdf could not be uploaded.");
  });
});
