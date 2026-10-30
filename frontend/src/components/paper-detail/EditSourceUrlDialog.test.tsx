import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/apiTransport";
import { EditSourceUrlDialog } from "./EditSourceUrlDialog";

const { updateSourceUrl, submit, toast } = vi.hoisted(() => ({
  updateSourceUrl: vi.fn(), submit: vi.fn(), toast: vi.fn(),
}));
vi.mock("@/lib/api/papers", () => ({ papersApi: { updateSourceUrl } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

beforeEach(() => vi.resetAllMocks());

describe("source URL editing failures", () => {
  it.each([
    ["direct", new ApiError(new Response(null, { status: 422 }), JSON.stringify({ detail: [{ msg: "URL is not allowed" }] })), "URL is not allowed"],
    ["pending", new ApiError(new Response(null, { status: 429 }), JSON.stringify({ detail: { code: "limited", message: "Try later", help: "/limits" } })), "Try later See /limits for help."],
    ["direct", new TypeError("Failed to fetch"), "Failed to fetch"],
    ["direct", null, "Failed to update source URL."],
    ["pending", null, "Failed to submit your edit. Please try again."],
  ] as const)("shows the canonical message and %s title", async (submitMode, error, description) => {
    updateSourceUrl.mockRejectedValue(error);
    submit.mockRejectedValue(error);
    const close = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
        <EditSourceUrlDialog onOpenChange={close} paperId="42"
          initialUrl="https://example.test/old" submitMode={submitMode} />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.clear(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "https://example.test/new");
    await user.click(screen.getByRole("button", { name: submitMode === "pending" ? "Submit for review" : "Save Changes" }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith({
      title: submitMode === "pending" ? "Could not submit edit" : "Could not save source URL",
      description, variant: "destructive",
    }));
    expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveValue("https://example.test/new");
    expect(submitMode === "pending" ? submit : updateSourceUrl).toHaveBeenCalledOnce();
    expect(submitMode === "pending" ? updateSourceUrl : submit).not.toHaveBeenCalled();
  });
});
