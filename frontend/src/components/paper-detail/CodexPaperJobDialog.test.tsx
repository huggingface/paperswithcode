import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { codexApi, type CodexPaperJob } from "@/lib/api/codex";
import { CodexPaperJobDialog } from "./CodexPaperJobDialog";

afterEach(() => vi.restoreAllMocks());

const job = (status: CodexPaperJob["status"], extra: Partial<CodexPaperJob> = {}) =>
  ({ id: "job-1", status, report: null, error: null, hf_job_url: null, ...extra }) as CodexPaperJob;

it("starts the kind's job, follows it to completion, and reports completion once", async () => {
  const start = vi.spyOn(codexApi, "startPaperJob").mockResolvedValue(job("running"));
  const get = vi.spyOn(codexApi, "getPaperJob").mockResolvedValue(job("completed", { report: "Added 2 rows." }));
  const onComplete = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={client}>
      <CodexPaperJobDialog kind="enrich-paper" paperId={42} paperTitle="Paper" triggerClassName="action-btn" onComplete={onComplete} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "enrich paper" }));
  fireEvent.click(screen.getByRole("button", { name: "Run enrich-paper" }));

  expect(await screen.findByText("Added 2 rows.")).toBeInTheDocument();
  expect(start).toHaveBeenCalledWith("enrich-paper", 42);
  expect(get).toHaveBeenCalledWith("enrich-paper", "job-1");
  await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: "Run again" })).toBeInTheDocument();
  client.clear();
});

it("shows the API error when a job cannot start", async () => {
  vi.spyOn(codexApi, "startPaperJob").mockRejectedValue(new Error("Codex is disabled."));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

  render(
    <QueryClientProvider client={client}>
      <CodexPaperJobDialog kind="add-evals" paperId={1} paperTitle="Paper" triggerClassName="edit-link" onComplete={vi.fn()} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "add evals" }));
  fireEvent.click(screen.getByRole("button", { name: "Run add-evals" }));

  expect(await screen.findByText("Codex is disabled.")).toBeInTheDocument();
});
