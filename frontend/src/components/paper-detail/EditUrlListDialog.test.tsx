import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EditUrlListDialog } from "./EditUrlListDialog";

const { updateRepositories, updateProjectPages, submit, toast } = vi.hoisted(() => ({
  updateRepositories: vi.fn(), updateProjectPages: vi.fn(), submit: vi.fn(), toast: vi.fn(),
}));
vi.mock("@/lib/api/papers", () => ({ papersApi: { updateRepositories, updateProjectPages } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

beforeEach(() => {
  vi.resetAllMocks();
  updateRepositories.mockResolvedValue(undefined);
  updateProjectPages.mockResolvedValue(undefined);
  submit.mockResolvedValue({ status: "pending" });
});

function renderDialog(props: Partial<Parameters<typeof EditUrlListDialog>[0]> = {}) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
      <EditUrlListDialog onOpenChange={vi.fn()} paperId="42" kind="repositories" initialItems={[]} {...props} />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("EditUrlListDialog", () => {
  it("saves a typed GitHub URL in canonical form", async () => {
    const user = renderDialog({ initialItems: [{ url: "https://github.com/a/one", is_official: true }] });
    await user.type(screen.getByRole("textbox"), "github.com/B/Two/");
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(updateRepositories).toHaveBeenCalledWith("42", [
      { url: "https://github.com/a/one", is_official: true },
      { url: "https://github.com/b/two", is_official: false },
    ]));
  });

  it("refuses a repository already listed under another spelling", async () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    const user = renderDialog({ initialItems: [{ url: "https://github.com/a/one", is_official: false }] });
    await user.type(screen.getByRole("textbox"), "https://github.com/A/one.git");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(alert).toHaveBeenCalledWith("This repository URL is already added");
    expect(screen.getAllByText(/github\.com/)).toHaveLength(1);
  });

  it("asks before a direct save removes a project page", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = renderDialog({ kind: "project_pages", initialItems: [{ url: "https://example.com/p", is_official: false }] });
    await user.click(screen.getByTitle("Remove project page"));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));
    expect(confirm).toHaveBeenCalledWith("Remove one or more project pages from this paper?");
    expect(updateProjectPages).not.toHaveBeenCalled();
  });

  it("submits a removal for review without asking", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const user = renderDialog({ submitMode: "pending", initialItems: [{ url: "https://github.com/a/one", is_official: false }] });
    await user.click(screen.getByTitle("Remove repository"));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit.mock.calls[0][0]).toMatchObject({ edit_type: "repositories", proposed_payload: { repositories: [] } });
    expect(confirm).not.toHaveBeenCalled();
  });
});
