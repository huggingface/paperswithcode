import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { evaluationChange, refreshEvaluationQueries } from "./evaluationQueryInvalidation";

const before = [
  { id: "1", paper_id: "42", task_id: "10", dataset_id: "100" },
  { id: "2", paper_id: "42", task_id: "20", dataset_id: "200" },
];
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000, retry: false } } });
  const entries = [
    { key: ["paper", "42"], data: { id: "42" } },
    { key: ["paper-arxiv", "2401.00001"], data: { id: "42" } },
    { key: ["paper-summary", "42"], data: { id: "42" } },
    { key: ["evaluations", "paper", "42"], data: before },
    { key: ["dataset-evals", "100"], data: [before[0]] },
    { key: ["dataset", "old", "with-paper"], data: { id: "100", leaderboard_summary: { value: 1 } } },
    { key: ["dataset-tasks", "100"], data: [{ id: "10" }] },
    { key: ["dataset-evals", "300"], data: [] },
    { key: ["dataset", "new", "with-paper", "new-task", "open"], data: { id: "300" } },
    { key: ["task-page", "old-task"], data: { task: { id: "10" }, benchmarks: [], subtask_benchmarks: [] } },
    { key: ["task-page", "parent"], data: { task: { id: "9" }, benchmarks: [], subtask_benchmarks: [{ subtask_id: "30", benchmarks: [] }] } },
    { key: ["task-benchmark-trends", "30", true], data: { task_id: "30" } },
    { key: ["task-benchmark-trends", "old-task"], data: { task_id: "10" } },
    { key: ["paper-search-feed", { q: "test" }], data: { pages: [] } },
  ];
  const unrelated = [
    { key: ["dataset-evals", "200"], data: [before[1]] },
    { key: ["dataset", "other"], data: { id: "200" } },
    { key: ["task-page", "other"], data: { task: { id: "20" }, benchmarks: [], subtask_benchmarks: [] } },
    { key: ["task-benchmark-trends", "other"], data: { task_id: "20" } },
    { key: ["evaluations", "paper", "99"], data: [] },
    { key: ["metric-directions"], data: {} },
  ];
  [...entries, ...unrelated].forEach(({ key, data }) => client.setQueryData(key, data));
  return { client, entries, unrelated };
}

describe("evaluation cache reconciliation", () => {
  it("invalidates old/new leaderboard rows, rank-bearing papers and summaries for a move", () => {
    const { client, entries, unrelated } = setup();
    refreshEvaluationQueries(client, evaluationChange("42", before, [
      { op: "update", evaluation_id: 1, data: { task_id: 30, dataset_id: 300, metrics: {} } },
    ], "2401.00001"));
    entries.forEach(({ key }) => expect(client.getQueryState(key)?.isInvalidated, JSON.stringify(key)).toBe(true));
    unrelated.forEach(({ key }) => expect(client.getQueryState(key)?.isInvalidated, JSON.stringify(key)).toBe(false));
  });

  it.each(["create", "delete"] as const)("refreshes a cached benchmark revisited after %s", async op => {
    const { client } = setup();
    refreshEvaluationQueries(client, evaluationChange("42", before, op === "create"
      ? [{ op, data: { task_id: 10, dataset_id: 100, metrics: {} } }]
      : [{ op, evaluation_id: 1 }]));
    const queryFn = vi.fn().mockResolvedValue([{ score: 99 }]);
    expect(await client.fetchQuery({ queryKey: ["dataset-evals", "100"], queryFn })).toEqual([{ score: 99 }]);
    expect(queryFn).toHaveBeenCalledOnce();
    expect(client.getQueryState(["dataset", "old", "with-paper"])?.isInvalidated).toBe(true);
    expect(client.getQueryState(["dataset-evals", "200"])?.isInvalidated).toBe(false);
  });
});

it("refreshes competing paper results and details without staling unrelated papers", () => {
  const { client } = setup();
  const peer = { id: "3", paper_id: "43", paper_arxiv_id: "peer-arxiv", task_id: "10", dataset_id: "100", best_rank: 1 };
  client.setQueryData(["evaluations", "paper", "43"], [peer]);
  client.setQueryData(["paper", "43"], { id: "43" });
  client.setQueryData(["paper-arxiv", "peer-arxiv"], { id: "43" });
  client.setQueryData(["evaluations", "paper", "44"], [{ ...peer, paper_id: "44", task_id: "20" }]);
  client.setQueryData(["paper", "44"], { id: "44" });
  refreshEvaluationQueries(client, evaluationChange("42", before, [{ op: "delete", evaluation_id: 1 }]));
  for (const key of [["evaluations", "paper", "43"], ["paper", "43"], ["paper-arxiv", "peer-arxiv"]]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  }
  for (const key of [["evaluations", "paper", "44"], ["paper", "44"]]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  }
});
