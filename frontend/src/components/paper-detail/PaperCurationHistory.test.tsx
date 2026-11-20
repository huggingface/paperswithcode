import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { codexApi, type CodexPaperJob } from "@/lib/api/codex";
import { PaperCurationHistory } from "./PaperCurationHistory";

afterEach(() => vi.restoreAllMocks());

const job = (id: string, status: CodexPaperJob["status"], extra: Partial<CodexPaperJob> = {}) =>
  ({
    id,
    kind: "enrich-paper",
    status,
    trigger: "hf-daily-cron",
    created_at: "2026-11-19T00:00:00Z",
    attempt_count: 0,
    trace_status: "pending",
    report: null,
    error: null,
    hf_job_url: null,
    validation_summary: null,
    mutation_result: null,
    ...extra,
  }) as CodexPaperJob;

it("lists the paper's jobs and explains a paused queue", async () => {
  const history = vi.spyOn(codexApi, "paperHistory").mockResolvedValue({
    paper_id: 133629,
    jobs: [
      job("queued-job", "queued"),
      job("done-job", "completed", { kind: "add-evals", report: "Added 3 rows.", trace_status: "complete" }),
    ],
    scheduler_pause: {
      dispatch_enabled: true,
      paused_at: "2026-11-20T03:06:00Z",
      pause_reason: "trace upload failures",
      pause_condition: "trace_upload_failures",
      job_ids: ["queued-job"],
    },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={client}>
      <PaperCurationHistory paperId={133629} />
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/2 jobs/)).toBeInTheDocument();
  expect(history).toHaveBeenCalledWith(133629);
  expect(screen.getByText(/scheduler dispatch paused since .*: trace upload failures/)).toBeInTheDocument();
  expect(screen.getByText("Added 3 rows.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "trace manifest" })).toHaveAttribute(
    "href",
    expect.stringContaining("/admin/codex-curation/jobs/done-job/trace"),
  );
  client.clear();
});
