import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EditDocumentTypeDialog } from "./EditDocumentTypeDialog";

const { updateDocumentType, toast } = vi.hoisted(() => ({
  updateDocumentType: vi.fn(), toast: vi.fn(),
}));
vi.mock("@/lib/api/papers", () => ({ papersApi: { updateDocumentType } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

beforeEach(() => vi.resetAllMocks());

function renderDialog(initialType: string, close = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <EditDocumentTypeDialog onOpenChange={close} paperId="42" initialType={initialType} />
    </QueryClientProvider>,
  );
  return close;
}

describe("EditDocumentTypeDialog", () => {
  it("saves the normalized type and closes", async () => {
    updateDocumentType.mockResolvedValue({ id: "42", document_type: "Technical Report" });
    const close = renderDialog("");
    const user = userEvent.setup();
    await user.type(screen.getByRole("combobox"), "  Technical   Report ");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(close).toHaveBeenCalledWith(false));
    expect(updateDocumentType).toHaveBeenCalledWith("42", "Technical Report");
  });

  it("clears the type when emptied", async () => {
    updateDocumentType.mockResolvedValue({ id: "42", document_type: null });
    renderDialog("Technical Report");
    const user = userEvent.setup();
    await user.clear(screen.getByRole("combobox"));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(updateDocumentType).toHaveBeenCalledWith("42", null));
  });

  it("keeps the dialog open and reports a failed save", async () => {
    updateDocumentType.mockRejectedValue(new TypeError("Failed to fetch"));
    const close = renderDialog("");
    const user = userEvent.setup();
    await user.type(screen.getByRole("combobox"), "System Card");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith({
      title: "Could not save document type", description: "Failed to fetch", variant: "destructive",
    }));
    expect(close).not.toHaveBeenCalled();
  });
});
