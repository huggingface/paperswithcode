import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EditTaxonomyTagsDialog } from "./EditTaxonomyTagsDialog";

const api = vi.hoisted(() => ({ listMethods: vi.fn() }));
vi.mock("@/lib/api/catalog", () => ({ catalogApi: { listMethods: api.listMethods } }));
vi.mock("@/lib/api/papers", () => ({ papersApi: { updateMethods: vi.fn() } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit: vi.fn() } }));
vi.mock("./SuggestTaxonomyDialog", () => ({ SuggestTaxonomyDialog: () => null }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

const grpo = { id: "1", name: "GRPO", slug: "grpo" };
const rsi = { id: "2", name: "Recursive Self-Improvement", slug: "rsi" };

describe("method search ordering", () => {
  it("lists search matches before non-matching selected methods", async () => {
    api.listMethods.mockImplementation(({ q }: { q?: string }) =>
      Promise.resolve({ results: q ? [rsi] : [grpo, rsi] }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><EditTaxonomyTagsDialog kind="method" onOpenChange={vi.fn()} paperId="42" initialItems={[grpo, rsi]} /></QueryClientProvider>);
    const names = () => screen.getAllByRole("checkbox").map(box => box.getAttribute("id"));
    await waitFor(() => expect(names()).toEqual(["method-1", "method-2"]));
    await userEvent.setup().type(screen.getByPlaceholderText("Search methods..."), "recursive");
    await waitFor(() => expect(names()).toEqual(["method-2", "method-1"]));
  });
});
