import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SuggestTaxonomyDialog } from "./SuggestTaxonomyDialog";

const { listTasks, listDatasets, submit } = vi.hoisted(() => ({
  listTasks: vi.fn(),
  listDatasets: vi.fn(),
  submit: vi.fn(),
}));

vi.mock("@/lib/api/catalog", () => ({
  catalogApi: { listTasks, listDatasets },
}));

vi.mock("@/lib/api/submissions", () => ({
  submissionsApi: { submit },
}));

const tasks = [
  { id: "9", name: "Image Classification", slug: "image-classification", level: 0 },
  { id: "14", name: "Object Detection", slug: "object-detection", level: 0 },
];

function renderDialog(kind: "benchmark" | "metric") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SuggestTaxonomyDialog
        open
        onOpenChange={vi.fn()}
        paperId="42"
        kind={kind}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listTasks.mockReset();
  listTasks.mockResolvedValue({ count: tasks.length, results: tasks });
  listDatasets.mockReset();
  listDatasets.mockImplementation(({ task_id }: { task_id?: number }) =>
    Promise.resolve(
      task_id === 9
        ? {
            count: 1,
            results: [{ id: "31", name: "ImageNet (ReaL)", slug: "imagenet-real" }],
          }
        : { count: 0, results: [] },
    ),
  );
  submit.mockReset();
  submit.mockResolvedValue(undefined);
});

describe("SuggestTaxonomyDialog", () => {
  it("selects benchmark tasks by name while submitting their internal IDs", async () => {
    const user = userEvent.setup();
    renderDialog("benchmark");

    expect(screen.queryByText("Intended task IDs")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Add intended task" }));
    await user.click(await screen.findByText("Image Classification"));
    await user.click(screen.getByRole("combobox", { name: "Add intended task" }));
    await user.click(await screen.findByText("Object Detection"));

    await user.type(screen.getByLabelText("Name"), "ImageNet Plus");
    await user.type(screen.getByLabelText("Description"), "An expanded benchmark.");
    await user.click(screen.getByRole("button", { name: "Submit suggestion" }));

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith({
        paper_id: 42,
        edit_type: "new_benchmark",
        proposed_payload: {
          name: "ImageNet Plus",
          description: "An expanded benchmark.",
          task_ids: [9, 14],
        },
      });
    });
  });

  it("selects a metric leaderboard by task and benchmark names", async () => {
    const user = userEvent.setup();
    renderDialog("metric");

    expect(screen.queryByPlaceholderText("Task ID")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Benchmark ID")).not.toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Select task" }));
    await user.click(await screen.findByText("Image Classification"));
    await user.click(screen.getByRole("combobox", { name: "Select benchmark" }));
    await user.click(await screen.findByText("ImageNet (ReaL)"));

    await user.type(screen.getByLabelText("Name"), "Adjusted Accuracy");
    await user.type(screen.getByLabelText("Description"), "Accuracy adjusted for label noise.");
    await user.click(screen.getByRole("button", { name: "Submit suggestion" }));

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith({
        paper_id: 42,
        edit_type: "new_metric",
        proposed_payload: {
          name: "Adjusted Accuracy",
          description: "Accuracy adjusted for label noise.",
          direction: "higher_is_better",
          task_id: 9,
          dataset_id: 31,
        },
      });
    });
  });

  it("distinguishes a failed task lookup from an empty task catalog", async () => {
    listTasks.mockRejectedValue(new Error("network unavailable"));
    const user = userEvent.setup();
    renderDialog("benchmark");

    await user.click(screen.getByRole("combobox", { name: "Add intended task" }));

    expect(await screen.findByText("Could not load tasks. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("No tasks found.")).not.toBeInTheDocument();
  });
});
