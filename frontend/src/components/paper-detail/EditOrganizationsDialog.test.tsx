import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditOrganizationsDialog } from "./EditOrganizationsDialog";

const { getOrganizations, updatePaperOrganizations, submit, onOpenChange } = vi.hoisted(() => ({
  onOpenChange: vi.fn(),
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
      <MemoryRouter>
      <EditOrganizationsDialog
        open
        onOpenChange={onOpenChange}
        paperId="42"
        initialOrganizationIds={initialOrganizationIds}
        submitMode={submitMode}
      />
      </MemoryRouter>
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
  onOpenChange.mockReset();
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

  it("ranks name-prefix matches above other substring matches", async () => {
    getOrganizations.mockResolvedValue({
      count: 3,
      results: [
        { id: "4", name: "Shanghai AI Lab", slug: "shanghai-ai-lab", is_featured: true },
        { id: "5", name: "Mistral AI", slug: "mistral-ai", is_featured: true },
        { id: "6", name: "Ai2", slug: "ai2", is_featured: true },
      ],
    });
    const user = userEvent.setup();
    renderDialog();

    await screen.findByText("Ai2");
    await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "ai");

    expect(screen.getAllByRole("checkbox").map((box) => box.closest("label")?.textContent)).toEqual([
      "Ai2",
      "Shanghai AI Lab",
      "Mistral AI",
    ]);
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

 it("lets anyone suggest a missing organization for review", async () => {
   const user = userEvent.setup();
   renderDialog([], "pending");
   await screen.findByText("NVIDIA");
   await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "Prime Intellect");

   expect(screen.getByRole("textbox", { name: "Organization name" })).toHaveValue("Prime Intellect");
   const submitButton = screen.getByRole("button", { name: "Submit organization" });
   expect(submitButton).toBeDisabled();
   await user.type(
     screen.getByRole("textbox", { name: "Hugging Face organization" }),
     "https://huggingface.co/PrimeIntellect",
   );
   await user.type(screen.getByRole("textbox", { name: "Website" }), "https://www.primeintellect.ai");
   await user.upload(
     screen.getByLabelText("Logo"),
     new File([new Uint8Array([137, 80, 78, 71])], "logo.png", { type: "image/png" }),
   );
   await screen.findByAltText("Selected logo");
   await user.click(submitButton);

   await screen.findByText(/was submitted for review/);
   expect(submit).toHaveBeenCalledWith({
     paper_id: 42,
     edit_type: "new_organization",
     proposed_payload: {
       name: "Prime Intellect",
       hf_slug: "https://huggingface.co/PrimeIntellect",
       website_url: "https://www.primeintellect.ai",
       image: { file_name: "logo.png", mime_type: "image/png", data_url: "data:image/png;base64,iVBORw==" },
     },
   });
 });

 it("adds an auto-approved organization suggestion straight to the paper", async () => {
   submit.mockResolvedValue({ id: "pending-2", status: "approved" });
   const client = renderDialog([], "pending");
   const user = userEvent.setup();
   await screen.findByText("NVIDIA");
   await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "General Reasoning");
   await user.type(screen.getByRole("textbox", { name: "Hugging Face organization" }), "GeneralReasoning");
   await user.click(screen.getByRole("button", { name: "Submit organization" }));

   await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
   expect(client.getQueryState(["paper", "42"])?.isInvalidated).toBe(true);
 });

 it("holds Save changes until a filled-in suggestion is submitted or cleared", async () => {
   const user = userEvent.setup();
   renderDialog();
   await screen.findByText("NVIDIA");
   const save = screen.getByRole("button", { name: "Save changes" });
   await user.type(screen.getByRole("searchbox", { name: "Search organizations" }), "General Reasoning");
   expect(save).toBeEnabled();

   await user.type(screen.getByRole("textbox", { name: "Hugging Face organization" }), "GeneralReasoning");
   expect(save).toBeDisabled();
   expect(screen.getByText(/Submit the organization above/)).toBeInTheDocument();

   await user.click(screen.getByRole("button", { name: "Clear organization search" }));
   expect(save).toBeEnabled();
   expect(updatePaperOrganizations).not.toHaveBeenCalled();
 });
