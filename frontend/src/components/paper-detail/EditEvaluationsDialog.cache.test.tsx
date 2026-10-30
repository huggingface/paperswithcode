import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EditEvaluationsDialog } from "./EditEvaluationsDialog";
import type { Evaluation } from "@/lib/api/evaluations.types";

const api = vi.hoisted(() => ({ batch: vi.fn(), submit: vi.fn(), datasets: vi.fn(), metrics: vi.fn(), toast: vi.fn() }));
vi.mock("@/lib/api/evaluations", () => ({ evaluationsApi: { batch: api.batch } }));
vi.mock("@/lib/api/submissions", () => ({ submissionsApi: { submit: api.submit } }));
vi.mock("@/lib/api/catalog", () => ({ catalogApi: { listDatasets: api.datasets, leaderboardMetrics: api.metrics } }));
vi.mock("./SuggestTaxonomyDialog", () => ({ SuggestTaxonomyDialog: () => null }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: api.toast }) }));
const row: Evaluation = {
  id: "1", paper_id: "42", task_id: "10", dataset_id: "100", model_name: "Original",
  task_name: "Task", dataset_name: "Benchmark", metrics: { Accuracy: 88 },
  uses_additional_data: false, is_open: true, created_at: "", updated_at: "",
};
const keys = [["paper", "42"], ["evaluations", "paper", "42"], ["dataset-evals", "100"]];
function setup(mode: "direct" | "pending" = "direct") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 300_000 } } });
  keys.forEach(key => client.setQueryData(key, [row]));
  const close = vi.fn();
  render(<QueryClientProvider client={client}><EditEvaluationsDialog onOpenChange={close} paperId="42" initialEvaluations={[row]} submitMode={mode} /></QueryClientProvider>);
  return { client, close };
}
beforeEach(() => {
  vi.clearAllMocks();
  api.datasets.mockResolvedValue({ results: [{ id: "100", name: "Benchmark" }] });
  api.metrics.mockResolvedValue([{ metric_name: "Accuracy", metric_direction: "higher_is_better" }]);
  api.batch.mockResolvedValue({ event_id: "saved" });
  api.submit.mockResolvedValue({ id: 1 });
});
describe("evaluation save cache lifecycle", () => {
  it.each(["success", "failed", "pending"] as const)("only reconciles applied saves: %s", async outcome => {
    if (outcome === "failed") api.batch.mockRejectedValue(new Error("Save failed"));
    const { client, close } = setup(outcome === "pending" ? "pending" : "direct");
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText("Model name"), " edited");
    await user.click(screen.getByRole("button", { name: outcome === "pending" ? "Submit for review" : "Save Changes" }));
    await waitFor(() => expect(outcome === "pending" ? api.submit : api.batch).toHaveBeenCalledOnce());
    if (outcome === "failed") await waitFor(() => expect(api.toast).toHaveBeenCalled());
    else await waitFor(() => expect(close).toHaveBeenCalledWith(false));
    keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(outcome === "success"));
    if (outcome === "pending") expect(api.batch).not.toHaveBeenCalled();
  });
  it("does not reconcile a no-op direct save", async () => {
    const { client } = setup();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Save Changes" }));
    expect(api.batch).not.toHaveBeenCalled();
    keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(false));
  });
});
