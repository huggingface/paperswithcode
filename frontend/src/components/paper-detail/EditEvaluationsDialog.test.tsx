import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditEvaluationsDialog } from "./EditEvaluationsDialog";

const { batch, submit, toast } = vi.hoisted(() => ({
  batch: vi.fn(), submit: vi.fn(), toast: vi.fn(),
}));
vi.mock("@/lib/api/evaluations", () => ({ evaluationsApi: { batch } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit } }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));
vi.mock("@/lib/api/catalog", () => ({ catalogApi: {
  listDatasets: vi.fn().mockResolvedValue({ results: [{ id: "7", name: "Benchmark" }, { id: "8", name: "Other benchmark" }] }),
  listTasks: vi.fn().mockResolvedValue({ results: [{ id: "3", name: "Task" }, { id: "4", name: "Other task" }] }),
  leaderboardMetrics: vi.fn().mockResolvedValue([
    { metric_id: "1", metric_name: "Accuracy", metric_direction: "higher_is_better" },
    { metric_id: "2", metric_name: "F1", metric_direction: "higher_is_better" },
  ]),
} }));

function renderDialog(submitMode: "direct" | "pending") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <EditEvaluationsDialog open onOpenChange={vi.fn()} paperId="11" submitMode={submitMode}
      initialEvaluations={[{
        id: "19", paper_id: "11", task_id: "3", dataset_id: "7",
        task_name: "Task", dataset_name: "Benchmark", model_name: "Model",
        metrics: { Accuracy: 0, F1: "88.5" }, best_metric: "Accuracy",
        is_open: true, uses_additional_data: false, created_at: "", updated_at: "",
      }]} />
  </QueryClientProvider>);
}

beforeEach(() => { vi.clearAllMocks(); batch.mockResolvedValue({}); submit.mockResolvedValue({}); });

describe.each(["direct", "pending"] as const)("lossless %s evaluation editing", (mode) => {
  it.each(["task", "dataset"])("requires fresh scores when the %s changes", async (changed) => {
    const user = userEvent.setup();
    renderDialog(mode);
    expect(await screen.findByPlaceholderText("44.9")).toHaveValue("0");
    if (changed === "task") {
      await user.click(screen.getAllByRole("combobox")[0]);
      await user.click(await screen.findByRole("option", { name: "Other task" }));
    }
    await user.click(screen.getAllByRole("combobox")[1]);
    await user.click(await screen.findByRole("option", { name: "Other benchmark" }));
    expect(screen.getByPlaceholderText("44.9")).toHaveValue("");
    const metric = await screen.findByRole("option", { name: "F1" });
    await user.selectOptions(metric.closest("select")!, "F1");
    await user.type(screen.getByPlaceholderText("44.9"), "72");
    await user.click(screen.getByRole("button", { name: mode === "direct" ? "Save Changes" : "Submit for review" }));
    if (mode === "direct") {
      await waitFor(() => expect(batch).toHaveBeenCalledWith(11, [expect.objectContaining({
        payload: expect.objectContaining({ metrics: { F1: "72" }, dataset_id: 8, task_id: changed === "task" ? 4 : 3 }),
      })]));
    } else {
      await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
        proposed_payload: { operations: [expect.objectContaining({
          data: expect.objectContaining({ metrics: { F1: "72" }, dataset_id: 8, task_id: changed === "task" ? 4 : 3 }),
        })] },
      })));
    }
  });

  it("shows zero and preserves all scores through the dialog submission path", async () => {
    const user = userEvent.setup();
    renderDialog(mode);
    expect(await screen.findByPlaceholderText("44.9")).toHaveValue("0");
    await user.type(screen.getByPlaceholderText("Model name"), " renamed");
    await user.click(screen.getByRole("button", { name: mode === "direct" ? "Save Changes" : "Submit for review" }));
    const expected = { model_name: "Model renamed", metrics: { Accuracy: 0, F1: "88.5" } };
    if (mode === "direct") {
      await waitFor(() => expect(batch).toHaveBeenCalledWith(11, [expect.objectContaining({
        operation: "update", evaluation_id: 19, payload: expect.objectContaining(expected),
      })]));
      expect(submit).not.toHaveBeenCalled();
    } else {
      await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
        proposed_payload: { operations: [expect.objectContaining({
          op: "update", evaluation_id: 19, data: expect.objectContaining(expected),
        })] },
      })));
      expect(batch).not.toHaveBeenCalled();
    }
  });

  it("rejects a colliding metric rename before either API is called", async () => {
    const user = userEvent.setup();
    renderDialog(mode);
    const option = await screen.findByRole("option", { name: "F1" });
    await user.selectOptions(option.closest("select")!, "F1");
    await user.click(screen.getByRole("button", { name: mode === "direct" ? "Save Changes" : "Submit for review" }));
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({
      description: expect.stringContaining('already has that score'), variant: "destructive",
    })));
    expect(batch).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
});
