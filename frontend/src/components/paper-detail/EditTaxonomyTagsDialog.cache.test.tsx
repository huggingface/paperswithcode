import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EditTaxonomyTagsDialog } from "./EditTaxonomyTagsDialog";

const api = vi.hoisted(() => ({ updateTasks: vi.fn(), submit: vi.fn(), listTasks: vi.fn() }));
vi.mock("@/lib/api/papers", () => ({ papersApi: { updateTasks: api.updateTasks } }));
vi.mock("@/lib/api/catalog", () => ({ catalogApi: { listTasks: api.listTasks } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit: api.submit } }));
vi.mock("./SuggestTaxonomyDialog", () => ({ SuggestTaxonomyDialog: () => null }));
const toast = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));
const task = { id: "7", name: "Classification", slug: "classification", level: 0 };
const original = { id: "42", arxiv_id: "2401.00001", tasks: [task] };
const keys = [["paper", "42"], ["paper", "2401.00001"], ["paper-arxiv", "2401.00001"]];
function setup(mode: "direct" | "pending" = "direct") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300_000 } } });
  keys.forEach(key => client.setQueryData(key, original));
  client.setQueryData(["task-papers-infinite", "classification"], [original]);
  render(<QueryClientProvider client={client}><EditTaxonomyTagsDialog kind="task" onOpenChange={vi.fn()} paperId="42" arxivId="2401.00001" initialItems={[task]} submitMode={mode} /></QueryClientProvider>);
  return client;
}
beforeEach(() => {
  vi.clearAllMocks();
  toast.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  api.listTasks.mockResolvedValue({ results: [task] });
});

describe("task-edit cache lifecycle", () => {
  it("restores each detail snapshot after an optimistic edit fails and leaves feeds fresh", async () => {
    let reject!: (reason: Error) => void;
    api.updateTasks.mockReturnValue(new Promise((_, fail) => { reject = fail; }));
    const client = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Classification" }));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(api.updateTasks).toHaveBeenCalled());
    keys.forEach(key => expect(client.getQueryData(key)).toEqual({ ...original, tasks: [] }));
    await act(async () => reject(new Error("Save failed")));
    await waitFor(() => keys.forEach(key => expect(client.getQueryData(key)).toEqual(original)));
    expect(client.getQueryState(["task-papers-infinite", "classification"])?.isInvalidated).toBe(false);
    expect(toast).toHaveBeenCalledOnce();
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Could not save tasks" }));
  });

  it("confirms a direct edit only after the server accepts it", async () => {
    const updated = { ...original, tasks: [] };
    api.updateTasks.mockResolvedValue(updated);
    const client = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Classification" }));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith({
      title: "Tasks updated", description: "Saved 0 tasks for this paper.",
    }));
    expect(api.updateTasks).toHaveBeenCalledWith("42", []);
    keys.forEach(key => expect(client.getQueryData(key)).toEqual(updated));
  });

  it("does not change live caches for a pending-only submission", async () => {
    api.submit.mockResolvedValue({ id: "pending-1" });
    const client = setup("pending");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Classification" }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await waitFor(() => expect(api.submit).toHaveBeenCalled());
    expect(api.updateTasks).not.toHaveBeenCalled();
    keys.forEach(key => expect(client.getQueryData(key)).toEqual(original));
    expect(client.getQueryState(["task-papers-infinite", "classification"])?.isInvalidated).toBe(false);
  });
});
