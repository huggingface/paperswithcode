import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { codexApi, type CodexPaperJob } from "@/lib/api/codex";
import { ApiError } from "@/lib/apiTransport";
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
      job("done-job", "completed", {
        kind: "add-evals",
        report: "Added 3 rows.",
        trace_status: "complete",
        agent_trace_url: "https://huggingface.co/buckets/o/b/tree/traces/done-job/session.jsonl",
        trace_files_url: "https://huggingface.co/buckets/o/b/tree/traces/done-job",
      }),
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
  expect(screen.getByRole("link", { name: "agent trace" })).toHaveAttribute(
    "href",
    "https://huggingface.co/buckets/o/b/tree/traces/done-job/session.jsonl",
  );
  expect(screen.getByRole("link", { name: "trace files" })).toHaveAttribute(
    "href",
    "https://huggingface.co/buckets/o/b/tree/traces/done-job",
  );
  client.clear();
});

const renderHistory = (client: QueryClient) =>
  render(
    <QueryClientProvider client={client}>
      <PaperCurationHistory paperId={133665} />
    </QueryClientProvider>,
  );

const emptyHistory = { paper_id: 133665, jobs: [job("done-job", "completed")], scheduler_pause: null };

it("keeps showing loaded jobs when a background refetch fails", async () => {
  const history = vi.spyOn(codexApi, "paperHistory").mockResolvedValueOnce(emptyHistory);
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  renderHistory(client);
  expect(await screen.findByText(/1 job/)).toBeInTheDocument();

  history.mockRejectedValue(new TypeError("Failed to fetch"));
  await act(() => client.refetchQueries({ queryKey: ["admin", "paperCurationHistory", 133665] }));

  expect(history).toHaveBeenCalledTimes(3);
  expect(client.getQueryState(["admin", "paperCurationHistory", 133665])?.status).toBe("error");
  await act(async () => {});
  expect(screen.getByText(/1 job/)).toBeInTheDocument();
  expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();
  client.clear();
});

it("retries a dropped connection once on first load", async () => {
  const history = vi
    .spyOn(codexApi, "paperHistory")
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValueOnce(emptyHistory);
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  renderHistory(client);

  expect(await screen.findByText(/1 job/)).toBeInTheDocument();
  expect(history).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();
  client.clear();
});

it("shows an HTTP error from the first load without retrying", async () => {
  const history = vi
    .spyOn(codexApi, "paperHistory")
    .mockRejectedValue(new ApiError(new Response(null, { status: 500, statusText: "Internal Server Error" }), ""));
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  renderHistory(client);

  await waitFor(() => expect(screen.getByText(/API request failed: 500/)).toBeInTheDocument());
  expect(history).toHaveBeenCalledTimes(1);
  client.clear();
});
