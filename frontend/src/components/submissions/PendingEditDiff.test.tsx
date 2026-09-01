import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PendingEditDiff from "@/components/submissions/PendingEditDiff";
import {
  PendingEditPayloadError,
  parsePendingPaperEdit,
  type PendingEditType,
} from "@/lib/pendingEdits";

vi.mock("@/lib/api/catalog", () => ({
  catalogApi: {
    getTask: vi.fn().mockResolvedValue({ id: "1", name: "Task one" }),
    getMethod: vi.fn().mockResolvedValue({ id: "1", name: "Method one" }),
    getDataset: vi.fn().mockResolvedValue({ id: "2", name: "Dataset two" }),
    organizations: vi.fn().mockResolvedValue({
      results: [{ id: "1", slug: "lab", name: "Lab one" }],
    }),
  },
}));

const base = {
  id: 1,
  paper_id: 10,
  hf_username: "reviewer",
  is_author: false,
  status: "pending",
  created_at: "2026-08-14T00:00:00Z",
  updated_at: "2026-08-14T00:00:00Z",
} as const;

const fixtures: Array<{
  type: PendingEditType;
  proposed: object;
  current?: object;
  expected: string;
  secondaryExpected?: string;
}> = [
  { type: "tasks", proposed: { task_ids: [1] }, current: { tasks: [{ id: 1, name: "Task one" }] }, expected: "Task one" },
  { type: "methods", proposed: { method_ids: [1] }, current: { methods: [{ id: 1, name: "Method one" }] }, expected: "Method one" },
  { type: "organizations", proposed: { organization_ids: [1] }, current: { organizations: [{ id: 1, name: "Lab one" }] }, expected: "Lab one" },
  { type: "repositories", proposed: { repositories: [{ url: "https://github.com/org/repo", is_official: true }] }, current: { repositories: [] }, expected: "https://github.com/org/repo" },
  { type: "project_pages", proposed: { project_pages: [{ url: "https://example.com/project", is_official: true }] }, current: { project_pages: [] }, expected: "https://example.com/project" },
  { type: "evaluations", proposed: { operations: [{ op: "create", data: { task_id: 1, dataset_id: 2, model_name: "Model one", metrics: { Accuracy: "90" } } }] }, current: { evaluations: [] }, expected: "Model one" },
  { type: "source_url", proposed: { source_url: "https://example.com/source" }, current: { source_url: null }, expected: "https://example.com/source" },
  { type: "hf_artifacts", proposed: { hf_models: ["https://huggingface.co/org/model"], hf_datasets: [], hf_spaces: [] }, current: { hf_models: [], hf_datasets: [], hf_spaces: [] }, expected: "https://huggingface.co/org/model" },
  { type: "new_task", proposed: { name: "New task" }, expected: "New task" },
  { type: "new_method", proposed: { name: "New method" }, expected: "New method" },
  { type: "new_benchmark", proposed: { benchmark: "New benchmark", task: "New task", description: "Benchmark description" }, expected: "New benchmark", secondaryExpected: "New task" },
  { type: "new_metric", proposed: { name: "New metric", description: "Metric description", direction: "higher_is_better", task_id: 1, dataset_id: 2 }, expected: "New metric" },
  { type: "new_conference", proposed: { name: "New conference", year: 2026, url: "https://example.com/conference" }, expected: "New conference" },
  { type: "new_external_paper", proposed: { title: "External paper", source_url: "https://example.com/paper", authors: ["Ada"], date_published: "2026-08-10" }, expected: "External paper" },
];

function renderFixture(fixture: typeof fixtures[number]) {
  const edit = parsePendingPaperEdit({
    ...base,
    edit_type: fixture.type,
    proposed_payload: fixture.proposed,
    current_payload: fixture.current ?? null,
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <PendingEditDiff edit={edit} />
    </QueryClientProvider>,
  );
}

describe("PendingEditDiff", () => {
  it.each(fixtures)("renders the $type contract", (fixture) => {
    renderFixture(fixture);
    expect(screen.getAllByText(fixture.expected).length).toBeGreaterThan(0);
    if (fixture.secondaryExpected) {
      expect(screen.getByText(fixture.secondaryExpected)).toBeInTheDocument();
    }
    expect(screen.queryByText(/No custom renderer exists/)).not.toBeInTheDocument();
  });

  it("rejects malformed payloads before rendering", () => {
    expect(() => parsePendingPaperEdit({
      ...base,
      edit_type: "organizations",
      proposed_payload: { organization_ids: ["not-a-number"] },
    })).toThrow(PendingEditPayloadError);
  });
});
