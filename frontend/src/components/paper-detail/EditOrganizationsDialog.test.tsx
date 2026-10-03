import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditOrganizationsDialog } from "./EditOrganizationsDialog";

const { getOrganizations, updatePaperOrganizations, submit } = vi.hoisted(() => ({
  submit: vi.fn(),
  getOrganizations: vi.fn(),
  updatePaperOrganizations: vi.fn(),
}));

vi.mock("@/lib/api/catalog", () => ({
  catalogApi: { organizations: getOrganizations },
}));

vi.mock("@/lib/api/papers", () => ({
  papersApi: { updateOrganizations: updatePaperOrganizations },
}));

vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit } }));

const organizations = {
  count: 3,
  results: [
    { id: "1", name: "NVIDIA", slug: "nvidia", is_featured: true },
    { id: "2", name: "ByteDance Seed", slug: "bytedance-seed", is_featured: true },
    { id: "3", name: "Google DeepMind", slug: "google-deepmind", is_featured: true },
  ],
};

function renderDialog(initialOrganizationIds: number[] = [], submitMode: "direct" | "pending" = "direct") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(["paper", "42"], { id: "42", title: "Original" });
  queryClient.setQueryData(["organization-papers-infinite", "nvidia"], []);
  render(
    <QueryClientProvider client={queryClient}>
      <EditOrganizationsDialog
        open
        onOpenChange={vi.fn()}
        paperId="42"
        initialOrganizationIds={initialOrganizationIds}
        submitMode={submitMode}
      />
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  getOrganizations.mockReset();
  getOrganizations.mockResolvedValue(organizations);
  updatePaperOrganizations.mockReset();
  updatePaperOrganizations.mockResolvedValue({ id: "42", title: "Updated" });
  submit.mockReset();
  submit.mockResolvedValue({ id: "pending-1" });
});

describe("EditOrganizationsDialog", () => {
  it("filters organizations by name without losing hidden selections", async () => {
    const user = userEvent.setup();
    renderDialog([1]);

    expect(await screen.findByText("NVIDIA")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "seed");

    expect(screen.getByText("ByteDance Seed")).toBeInTheDocument();
    expect(screen.queryByText("NVIDIA")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear organization search" }));
    expect(screen.getByRole("checkbox", { name: "NVIDIA" })).toBeChecked();
  });

  it("shows an empty state when the search has no matches", async () => {
    const user = userEvent.setup();
    renderDialog();

    await screen.findByText("NVIDIA");
    await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "missing");

    expect(screen.getByText('No organizations found matching "missing"')).toBeInTheDocument();
  });
});

 it("reconciles a direct organization edit without leaving its feed fresh", async () => {
   const client = renderDialog();
   const user = userEvent.setup();
   await user.click(await screen.findByRole("checkbox", { name: "NVIDIA" }));
   await user.click(screen.getByRole("button", { name: "Save changes" }));
   await waitFor(() => expect(client.getQueryData(["paper", "42"])).toEqual({ id: "42", title: "Updated" }));
   expect(client.getQueryState(["organization-papers-infinite", "nvidia"])?.isInvalidated).toBe(true);
 });

 it("leaves live caches alone when submitting organizations for review", async () => {
   const client = renderDialog([], "pending");
   const user = userEvent.setup();
   await user.click(await screen.findByRole("checkbox", { name: "NVIDIA" }));
   await user.click(screen.getByRole("button", { name: "Submit test edit" }));
   await waitFor(() => expect(submit).toHaveBeenCalled());
   expect(updatePaperOrganizations).not.toHaveBeenCalled();
   expect(client.getQueryData(["paper", "42"])).toEqual({ id: "42", title: "Original" });
   expect(client.getQueryState(["organization-papers-infinite", "nvidia"])?.isInvalidated).toBe(false);
 });
