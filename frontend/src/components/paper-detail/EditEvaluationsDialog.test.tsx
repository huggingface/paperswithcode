import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { catalogApi } from "@/lib/api/catalog";
import type { Evaluation } from "@/lib/api/evaluations.types";
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

const stored: Evaluation = {
  id: "19", paper_id: "11", task_id: "3", dataset_id: "7",
  task_name: "Task", dataset_name: "Benchmark", model_name: "Model",
  metrics: { Accuracy: 0, F1: "88.5" }, best_metric: "Accuracy",
  is_open: true, uses_additional_data: false, created_at: "", updated_at: "",
};

function renderDialog(submitMode: "direct" | "pending", isAdmin = false) {
  const onOpenChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <EditEvaluationsDialog onOpenChange={onOpenChange} paperId="11" submitMode={submitMode} isAdmin={isAdmin}
      initialEvaluations={[stored]} />
  </QueryClientProvider>);
  return { onOpenChange };
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
    expect(await screen.findByRole("alert")).toHaveTextContent("already has that score");
    expect(batch).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
  it("blocks a mixed valid/incomplete batch, then submits the complete corrected draft", async () => {
    const user = userEvent.setup();
    const { onOpenChange } = renderDialog(mode);
    await user.type(await screen.findByPlaceholderText("Model name"), " renamed");
    await user.click(screen.getByRole("button", { name: "Add Row" }));
    const save = screen.getByRole("button", { name: mode === "direct" ? "Save Changes" : "Submit for review" });
    await user.click(save);
    expect(screen.getByRole("alert")).toHaveTextContent("Row 2: Select a valid task.");
    expect(batch).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getAllByPlaceholderText("Model name")[0]).toHaveValue("Model renamed");
    // Discard the incomplete new row, then introduce and correct a required field on the edit.
    await user.click(screen.getByRole("button", { name: "Remove row" }));
    const score = screen.getByPlaceholderText("44.9");
    await user.clear(score);
    await user.click(save);
    expect(screen.getByRole("alert")).toHaveTextContent("Row 1: Enter a metric value.");
    expect(score).toHaveAttribute("aria-invalid", "true");
    expect(score).toHaveAccessibleDescription("Enter a metric value.");
    expect(batch).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
    await user.type(score, "0");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(save);
    await waitFor(() => expect(mode === "direct" ? batch : submit).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("reports an unchanged draft explicitly without calling either API", async () => {
    const user = userEvent.setup();
    renderDialog(mode);
    await screen.findByPlaceholderText("44.9");
    await user.click(screen.getByRole("button", { name: mode === "direct" ? "Save Changes" : "Submit for review" }));
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "No changes to submit" }));
    expect(batch).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });

});

it("numbers validation errors by visible rows after deleting an existing result", async () => {
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  renderDialog("direct", true);
  await screen.findByPlaceholderText("44.9");
  await user.click(screen.getByRole("button", { name: "Remove row" }));
  await user.click(screen.getByRole("button", { name: "Add Row" }));
  await user.click(screen.getByRole("button", { name: "Save Changes" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Row 1: Select a valid task.");
  expect(screen.getByRole("alert")).not.toHaveTextContent("Row 2:");
  expect(batch).not.toHaveBeenCalled();
  confirm.mockRestore();
});

it("submits a valid deletion even when the removed row has an incomplete score", async () => {
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  renderDialog("direct", true);
  await user.clear(await screen.findByPlaceholderText("44.9"));
  await user.click(screen.getByRole("button", { name: "Remove row" }));
  await user.click(screen.getByRole("button", { name: "Save Changes" }));
  await waitFor(() => expect(batch).toHaveBeenCalledWith(11, [{ operation: "delete", evaluation_id: 19 }]));
  expect(submit).not.toHaveBeenCalled();
  confirm.mockRestore();
});

it("starts from evaluations that finish loading after the editor opened", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const dialog = (evaluations: Evaluation[]) => (
    <QueryClientProvider client={client}>
      <EditEvaluationsDialog onOpenChange={vi.fn()} paperId="11" initialEvaluations={evaluations} />
    </QueryClientProvider>
  );
  const { rerender } = render(dialog([]));
  expect(screen.getByText("No evaluation results yet")).toBeInTheDocument();
  rerender(dialog([stored]));
  expect(await screen.findByPlaceholderText("Model name")).toHaveValue("Model");
});

it("reports a metric lookup failure instead of an empty metric list", async () => {
  vi.mocked(catalogApi.leaderboardMetrics).mockRejectedValueOnce(new Error("offline"));
  renderDialog("direct");
  expect(await screen.findByText("Could not load metrics")).toBeInTheDocument();
  expect(screen.queryByText("No configured metrics")).not.toBeInTheDocument();
});

it("keeps an existing harness by waiting for the benchmark's harness support", async () => {
  let resolveDatasets!: (value: Awaited<ReturnType<typeof catalogApi.listDatasets>>) => void;
  vi.mocked(catalogApi.listDatasets).mockReturnValueOnce(new Promise((resolve) => { resolveDatasets = resolve; }));
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <EditEvaluationsDialog onOpenChange={vi.fn()} paperId="11" submitMode="direct"
      initialEvaluations={[{ ...stored, harness: "lm-eval" }]} />
  </QueryClientProvider>);
  const save = screen.getByRole("button", { name: "Save Changes" });
  expect(save).toBeDisabled();

  resolveDatasets({ results: [{ id: "7", name: "Benchmark", supports_harness: true }] } as never);
  await waitFor(() => expect(save).toBeEnabled());
  await user.clear(screen.getByPlaceholderText("Model name"));
  await user.type(screen.getByPlaceholderText("Model name"), "Model v2");
  await user.click(save);
  await waitFor(() => expect(batch).toHaveBeenCalledWith(11, [expect.objectContaining({
    payload: expect.objectContaining({ model_name: "Model v2", harness: "lm-eval" }),
  })]));
});
