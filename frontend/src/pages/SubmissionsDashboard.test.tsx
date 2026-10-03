import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PendingPaperEdit } from "@/lib/pendingEdits";
import { parsePendingPaperEdit } from "@/lib/pendingEdits";
import SubmissionsDashboard from "@/pages/SubmissionsDashboard";

const { listPendingPaperEdits, approve } = vi.hoisted(() => ({
  listPendingPaperEdits: vi.fn(),
  approve: vi.fn(),
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: { is_admin: true },
    isLoading: false,
  }),
}));

vi.mock("@/lib/api/papers", () => ({
  papersApi: { get: vi.fn().mockResolvedValue({ id: "42", arxiv_id: "2401.00001", title: "Cached paper" }) },
}));

vi.mock("@/lib/api/submissions", () => ({
  submissionsApi: {
    list: listPendingPaperEdits,
    approve,
    reject: vi.fn(),
  },
}));

const externalPaperSubmission: PendingPaperEdit = {
  id: 1103,
  paper_id: null,
  hf_username: "submitter",
  is_author: false,
  edit_type: "new_external_paper",
  proposed_payload: {
    title: "A useful external paper",
    source_url: "https://example.com/paper",
    authors: ["Example Author"],
    date_published: "2026-08-10",
  },
  status: "pending",
  created_at: "2026-08-10T07:00:00Z",
  updated_at: "2026-08-10T07:00:00Z",
};

function taxonomySubmission(
  id: number,
  editType: "new_task" | "new_method" | "new_benchmark" | "new_metric" | "new_conference",
): PendingPaperEdit {
  const payloads = {
    new_task: { name: `Suggestion ${id}` },
    new_method: { name: `Suggestion ${id}`, source_url: "https://example.com/method" },
    new_benchmark: { benchmark: `Suggestion ${id}`, task: "Suggested task", description: "Description" },
    new_metric: {
      name: `Suggestion ${id}`,
      description: "Description",
      direction: "higher_is_better",
      task_id: 1,
      dataset_id: 2,
    },
    new_conference: { name: `Suggestion ${id}`, year: 2026, url: "https://example.com/conf" },
  } as const;
  return parsePendingPaperEdit({
    ...externalPaperSubmission,
    id,
    edit_type: editType,
    proposed_payload: payloads[editType],
  });
}

function renderDashboard(queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })) {
  return render(
    <QueryClientProvider client={queryClient}>
      <SubmissionsDashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listPendingPaperEdits.mockReset();
  listPendingPaperEdits.mockResolvedValue({
    count: 1,
    results: [externalPaperSubmission],
  });
});

describe("SubmissionsDashboard", () => {
  it("shows a controlled error when pending-edit data is malformed", async () => {
    listPendingPaperEdits.mockRejectedValue(
      new Error("Malformed pending-edit payload: proposed_payload.task_ids: Required"),
    );

    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not display submissions.");
    expect(screen.getByRole("alert")).toHaveTextContent("Malformed pending-edit payload");
    expect(screen.queryByText("No pending submissions.")).not.toBeInTheDocument();
  });

  it("does not expose low-level Codex review evidence", async () => {
    listPendingPaperEdits.mockResolvedValue({
      count: 1,
      results: [
        {
          ...externalPaperSubmission,
          review_evidence: {
            model: "codex",
            duplicate_checks: ["internal-only detail"],
          },
        },
      ],
    });

    renderDashboard();

    expect(
      await screen.findByText("External paper", { selector: ".submission-title" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Codex review artifact")).not.toBeInTheDocument();
    expect(screen.queryByText(/internal-only detail/)).not.toBeInTheDocument();
  });

  it("does not repeat a submitter-visible reason that matches the admin note", async () => {
    listPendingPaperEdits.mockResolvedValue({
      count: 1,
      results: [
        {
          ...externalPaperSubmission,
          status: "approved",
          admin_note: "The submission is valid.",
          user_review_reason: "The submission is valid.",
        },
      ],
    });

    renderDashboard();

    expect(await screen.findByText(/Admin note:/)).toHaveTextContent(
      "The submission is valid.",
    );
    expect(screen.queryByText(/Submitter-visible reason:/)).not.toBeInTheDocument();
  });

  it("shows a distinct submitter-visible reason", async () => {
    listPendingPaperEdits.mockResolvedValue({
      count: 1,
      results: [
        {
          ...externalPaperSubmission,
          status: "approved",
          admin_note: "Internal context.",
          user_review_reason: "Public explanation.",
        },
      ],
    });

    renderDashboard();

    expect(await screen.findByText(/Admin note:/)).toHaveTextContent("Internal context.");
    expect(screen.getByText(/Submitter-visible reason:/)).toHaveTextContent(
      "Public explanation.",
    );
  });

  it("labels and filters external paper submissions separately from taxonomy suggestions", async () => {
    const user = userEvent.setup();
    renderDashboard();

    expect(
      await screen.findByText("External paper", { selector: ".submission-title" }),
    ).toBeInTheDocument();
    expect(screen.getByText("External paper submission")).toBeInTheDocument();
    expect(screen.queryByText("Taxonomy directory")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "external paper" }));

    await waitFor(() =>
      expect(listPendingPaperEdits).toHaveBeenCalledWith(
        expect.objectContaining({ edit_type: "new_external_paper" }),
      ),
    );
  });

  it("uses type-specific titles for taxonomy suggestions", async () => {
    const submissions = [
      taxonomySubmission(1, "new_task"),
      taxonomySubmission(2, "new_method"),
      taxonomySubmission(3, "new_benchmark"),
      taxonomySubmission(4, "new_metric"),
      taxonomySubmission(5, "new_conference"),
    ];
    listPendingPaperEdits.mockResolvedValue({
      count: submissions.length,
      results: submissions,
    });

    renderDashboard();

    for (const title of ["New task", "New method", "New benchmark", "New metric", "New conference"]) {
      expect(await screen.findByText(title, { selector: ".submission-title" })).toBeInTheDocument();
    }
    for (const subtitle of [
      "Task suggestion",
      "Method suggestion",
      "Benchmark suggestion",
      "Metric suggestion",
      "Conference suggestion",
    ]) {
      expect(screen.getByText(subtitle)).toBeInTheDocument();
    }
    expect(screen.queryByText("Taxonomy directory")).not.toBeInTheDocument();
  });
});

it.each(["tasks", "organizations"] as const)("invalidates route details and feeds when a %s edit is approved", async (edit_type) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300_000 } } });
  const paper = { id: "42", arxiv_id: "2401.00001", title: "Cached paper" };
  client.setQueryData(["paper-summary", "42"], paper);
  client.setQueryData(["paper", paper.arxiv_id], paper);
  client.setQueryData(["paper-preview", paper.arxiv_id], paper);
  client.setQueryData(["organization-papers-infinite", "nvidia"], [paper]);
  const submission = { ...externalPaperSubmission, paper_id: 42, edit_type, proposed_payload: edit_type === "tasks" ? { task_ids: [1] } : { organization_ids: [1] } };
  listPendingPaperEdits.mockResolvedValue({ count: 1, results: [submission] });
  approve.mockResolvedValue({ ...submission, status: "approved" });
  renderDashboard(client);
  await userEvent.setup().click(await screen.findByRole("button", { name: "Approve" }));
  await waitFor(() => expect(client.getQueryState(["paper", paper.arxiv_id])?.isInvalidated).toBe(true));
  expect(client.getQueryState(["paper-preview", paper.arxiv_id])?.isInvalidated).toBe(true);
  expect(client.getQueryState(["organization-papers-infinite", "nvidia"])?.isInvalidated).toBe(true);
});
