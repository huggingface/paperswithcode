import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { Paper } from "@/lib/api/papers.types";
import { evaluationChange, invalidatePaperDetails, patchPaperCaches, refreshEvaluationQueries, refreshPaperQueries } from "./cacheSync";

const updatedPaper = { id: "42", arxiv_id: "2401.00001", title: "Updated title" } as Paper;

// Keep these concrete keys independent of the registry: missing a reader family
// from reconciliation must fail this coverage check.
const feeds = [
  ["papers-infinite", { has_code: true }],
  ["paper-search-feed", { q: "old title" }],
  ["task-papers-infinite", "classification"],
  ["conference-papers-infinite", "cvpr-2026"],
  ["organization-papers-infinite", "example"],
  ["method-papers-infinite", "transformer"],
  ["my-bookmarks"],
  ["related-papers", "99"],
  ["paper-versions", "2401.00001"],
  ["paper-search", "old title", 8],
  ["chat-paper-mention-search", "old title"],
  ["trending-papers"],
  ["research-feed", "subject", {}],
];

describe("paper mutation reconciliation", () => {
  it.each(feeds.map(key => [key[0], key]))("refreshes %s when revisited, without an immediate request", async (_, queryKey) => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000, retry: false } } });
    const queryFn = vi.fn().mockResolvedValue([updatedPaper]);
    const key = queryKey as readonly unknown[];
    client.setQueryData(key, [{ ...updatedPaper, title: "Before edit" }]);
    const observer = new QueryObserver(client, { queryKey: key, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    refreshPaperQueries(client, updatedPaper, ["42"]);
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    expect(queryFn).not.toHaveBeenCalled();
    unsubscribe();
    const revisited = new QueryObserver(client, { queryKey: key, queryFn });
    const leave = revisited.subscribe(() => {});
    await vi.waitFor(() => expect(revisited.getCurrentResult().data).toEqual([updatedPaper]));
    expect(queryFn).toHaveBeenCalledTimes(1);
    leave();
    client.clear();
  });

  it("reconciles detail aliases and previews without refetching unrelated queries", () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000 } } });
    const detailKeys = [["paper", "42"], ["paper", "2401.00001"], ["paper-summary", "2401.00001"], ["paper-summary", "42"]];
    const queryFn = vi.fn();
    const unsubscribes = detailKeys.map(queryKey => {
      client.setQueryData(queryKey, { ...updatedPaper, title: "Before edit" });
      return new QueryObserver(client, { queryKey, queryFn }).subscribe(() => {});
    });
    client.setQueryData(["organizations", "curation"], ["untouched"]);
    client.setQueryData(["paper", "99"], { id: "99" });
    refreshPaperQueries(client, updatedPaper, ["42", "2401.00001"]);
    detailKeys.forEach(key => {
      expect(client.getQueryData(key)).toEqual(updatedPaper);
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    });
    expect(client.getQueryState(["organizations", "curation"])?.isInvalidated).toBe(false);
    expect(client.getQueryData(["paper", "99"])).toEqual({ id: "99" });
    expect(queryFn).not.toHaveBeenCalled();
    unsubscribes.forEach(unsubscribe => unsubscribe());
    client.clear();
  });
});

it("invalidates all detail aliases after approval without fetching inactive cards", () => {
  const client = new QueryClient();
  const keys = [["paper", "42"], ["paper", "2401.00001"], ["paper-summary", "2401.00001"], ["paper-summary", "42"]];
  keys.forEach(key => client.setQueryData(key, updatedPaper));
  client.setQueryData(["paper", "99"], { id: "99" });
  invalidatePaperDetails(client, ["42", "2401.00001"]);
  keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(true));
  expect(client.getQueryState(["paper", "99"])?.isInvalidated).toBe(false);
  client.clear();
});

it("rolls back every cached copy of a paper when an optimistic edit fails", async () => {
  const client = new QueryClient();
  const keys = [["paper", "42"], ["paper", "2401.00001"], ["paper-summary", "2401.00001"], ["paper-summary", "42"]];
  keys.forEach(key => client.setQueryData(key, updatedPaper));
  const rollback = await patchPaperCaches(client, ["42", "2401.00001"], paper => ({ ...paper, title: "Optimistic" }));
  keys.forEach(key => expect(client.getQueryData<Paper>(key)?.title).toBe("Optimistic"));
  rollback();
  keys.forEach(key => expect(client.getQueryData(key)).toEqual(updatedPaper));
  client.clear();
});


const before = [
  { id: "1", paper_id: "42", task_id: "10", dataset_id: "100" },
  { id: "2", paper_id: "42", task_id: "20", dataset_id: "200" },
];
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000, retry: false } } });
  const entries = [
    { key: ["paper", "42"], data: { id: "42" } },
    { key: ["paper", "2401.00001"], data: { id: "42" } },
    { key: ["paper-summary", "42"], data: { id: "42" } },
    { key: ["paper-evals", "42"], data: before },
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
    { key: ["paper-evals", "99"], data: [] },
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
  client.setQueryData(["paper-evals", "43"], [peer]);
  client.setQueryData(["paper", "43"], { id: "43" });
  client.setQueryData(["paper", "peer-arxiv"], { id: "43" });
  client.setQueryData(["paper-evals", "44"], [{ ...peer, paper_id: "44", task_id: "20" }]);
  client.setQueryData(["paper", "44"], { id: "44" });
  refreshEvaluationQueries(client, evaluationChange("42", before, [{ op: "delete", evaluation_id: 1 }]));
  for (const key of [["paper-evals", "43"], ["paper", "43"], ["paper", "peer-arxiv"]]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  }
  for (const key of [["paper-evals", "44"], ["paper", "44"]]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  }
});
