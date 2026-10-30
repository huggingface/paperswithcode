import type { ReactElement } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CronJobCard } from "@/components/cron/CronJobCard";
import { chatApi, type ChatSandboxSpendStatus } from "@/lib/api/chat";
import { operationsApi, type CronJobsResponse, type CronJobStatus, type PaperMarkdownJobsResponse } from "@/lib/api/operations";
import {
  ChatComputePanel,
  CronSnapshotNotice,
  cronStatusRefetchInterval,
} from "./CronDashboard";
import CronDashboard from "./CronDashboard";

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: { username: "nielsr", is_admin: true },
  }),
}));

vi.mock("@/lib/apiUrl", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/apiUrl")>()),
  isStagingEnvironment: () => false,
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const status = (overrides: Partial<ChatSandboxSpendStatus> = {}): ChatSandboxSpendStatus => ({
  environment: "staging",
  provider_mode: "starter_workspace",
  billing_cycle: "2026-08-01",
  cycle_end_at: "2026-09-01T00:00:00Z",
  circuit_state: "armed",
  trip_reason: null,
  tripped_at: null,
  estimated_microusd: 10_000_000,
  provider_floor_microusd: 9_000_000,
  effective_microusd: 10_000_000,
  warning_microusd: 75_000_000,
  application_cap_microusd: 100_000_000,
  environment_cap_microusd: null,
  workspace_cap_microusd: 250_000_000,
  remaining_microusd: 90_000_000,
  reconciliation_state: "fresh",
  last_metered_at: "2026-08-03T12:00:00Z",
  last_reconciled_at: "2026-08-03T12:00:00Z",
  last_reconciliation_attempt_at: "2026-08-03T12:00:00Z",
  next_reconciliation_at: "2026-08-03T13:00:00Z",
  live_count: 1,
  termination_uncertain_count: 0,
  live_states: { starting: 0, blank: 1, busy: 0, idle: 0, draining: 0, termination_uncertain: 0 },
  burn_rate_microusd_per_hour: null,
  projected_cap_hit_at: null,
  prior_cycle: null,
  daily_spend: [{ date: "2026-08-03", blank_pool_microusd: 1_000_000, assigned_microusd: 9_000_000 }],
  events: [],
  ...overrides,
});

describe("ChatComputePanel", () => {
  it.each([
    ["fresh", status(), "Fresh"],
    ["stale", status({ reconciliation_state: "stale" }), "Stale"],
    ["warning", status({ circuit_state: "warning" }), "Operator warning"],
    ["tripped", status({ circuit_state: "tripped", trip_reason: "application_cap" }), "Chat disabled"],
    ["empty", status({ live_count: 0, daily_spend: [] }), "No compute recorded in this cycle."],
    ["unavailable", status({ reconciliation_state: "unavailable", last_reconciled_at: null, next_reconciliation_at: null }), "Unavailable"],
  ])("renders %s state", (_name, data, expected) => {
    render(<ChatComputePanel data={data as ChatSandboxSpendStatus} loading={false} error={null} />);
    expect(screen.getAllByText(expected as string).length).toBeGreaterThan(0);
  });
});

const renderWithClient = (ui: ReactElement) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: ReactElement) => <QueryClientProvider client={client}>{node}</QueryClientProvider>;
  const result = render(wrap(ui));
  return { ...result, rerender: (next: ReactElement) => result.rerender(wrap(next)) };
};

describe("CronJobCard health axes", () => {
  const job: CronJobStatus = {
    job_name: "example",
    display_name: "Example scheduled job",
    category: "hourly",
    dashboard_group: "operations",
    status: "broken",
    status_reason: "Execution: scheduled workflow failed; Output: fresh output",
    last_run: "2026-08-14T12:00:00Z",
    last_db_write: "2026-08-14T12:01:00Z",
    recent_write_count: 10,
    duration: 30,
    is_running: false,
    error: null,
    schedule: "0 * * * *",
    critical: true,
    execution_health: {
      status: "broken",
      reason: "scheduled workflow failed",
      scheduler: "github_actions",
      last_expected_at: "2026-08-14T12:00:00Z",
      last_started_at: "2026-08-14T12:00:30Z",
      last_completed_at: "2026-08-14T12:01:00Z",
      next_expected_at: "2026-08-14T13:00:00Z",
    },
    output_health: {
      status: "healthy",
      reason: "fresh output",
      last_verified_at: "2026-08-14T12:01:00Z",
    },
    diagnostic_groups: {
      scheduler_orchestration: ["scheduled workflow failed"],
      credential_provider: [],
    },
    health_findings: [{
      plane: "scheduler",
      contract: "scheduler_execution",
      state: "degraded",
      summary: "scheduled workflow failed",
      evidence: { conclusion: "failure" },
    }],
    operator_url: "/autonomous-operations?operator=cron",
    run_url: "https://github.com/huggingface/paperswithcode/actions/runs/123",
  };

  it("renders axes independently and exposes scheduler evidence", () => {
    const { rerender } = renderWithClient(
      <CronJobCard job={job} expanded={false} onToggle={() => undefined} />,
    );
    expect(screen.getByText("Execution: broken")).toBeInTheDocument();
    expect(screen.getByText("Output: healthy")).toBeInTheDocument();
    expect(screen.getByText("broken")).toBeInTheDocument();

    rerender(<CronJobCard job={job} expanded={true} onToggle={() => undefined} />);
    expect(screen.getByText("Scheduler evidence")).toBeInTheDocument();
    expect(screen.getByText("github_actions")).toBeInTheDocument();
    expect(screen.getByText("Deterministic contract findings")).toBeInTheDocument();
    expect(screen.getByText("Conclusion: failure")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open operator" })).toHaveAttribute(
      "href",
      "/autonomous-operations?operator=cron",
    );
    expect(screen.getByRole("link", { name: "Open run" })).toHaveAttribute(
      "href",
      "https://github.com/huggingface/paperswithcode/actions/runs/123",
    );
    rerender(<CronJobCard job={{ ...job, recent_write_count: 11 }} expanded={true} onToggle={() => undefined} />);
    expect(screen.getByText("Scheduler evidence")).toBeInTheDocument();
  });

  it("explains paper Markdown spend, reservations, and rolling window", async () => {
    const budget = {
      mode: "live" as const,
      cost_policy: "unmetered_hf" as const,
      budget_enforced: false,
      window: "rolling_30_days" as const,
      window_days: 30,
      window_started_at: "2026-07-18T12:00:00Z",
      next_release_at: "2026-08-20T12:00:00Z",
      next_release_usd: 4.5,
      spent_usd: 86.73,
      active_reserved_usd: 0,
      desired_jobs: 1,
      affordable_jobs: 1,
      planned_jobs: 1,
      planned_reserved_usd: 12.6,
      current_exposure_usd: 86.73,
      projected_usd: 99.33,
      ceiling_usd: 100,
      headroom_usd: 13.27,
      can_launch_planned: true,
      hourly_rate_usd: 1.8,
      reservation_hours_per_job: 12,
      reservation_per_job_usd: 21.6,
      relevant_jobs: 5,
    };
    const monitor: PaperMarkdownJobsResponse = {
      available: true,
      namespace: "huggingface",
      jobs: [
        {
          id: "job-omitted-image",
          url: "https://huggingface.co/jobs/huggingface/job-omitted-image",
          stage: "COMPLETED",
          effective_outcome: "success",
          mode: "backfill",
          progress: {
            status: "completed",
            total_papers: 1,
            processed_papers: 1,
            succeeded_papers: 1,
            failed_papers: 0,
            already_existed_papers: 0,
            extracted_images: 3,
            omitted_images: 2,
            error_samples: [],
          },
        },
      ],
      summary: {
        logical_shards: 6,
        provider_attempts: 7,
        recovered_mount_failures: 1,
        unresolved_mount_failures: 0,
      },
      selected_profiles: {
        live: {
          profile_id: "live-v1",
          mode: "live",
          max_papers: 50,
          concurrency: 1,
          hard_timeout_seconds: 21600,
          soft_deadline_seconds: 19800,
          reservation_hours: 6,
          reservation_per_job_usd: 10.8,
        },
        backfill: {
          profile_id: "backfill-v1",
          mode: "backfill",
          max_papers: 50,
          concurrency: 4,
          hard_timeout_seconds: 21600,
          soft_deadline_seconds: 19800,
          reservation_hours: 6,
          reservation_per_job_usd: 10.8,
        },
      },
      budgets: {
        live: budget,
        backfill: {
          ...budget,
          mode: "backfill",
          window: "all_history",
          window_days: null,
          next_release_at: null,
          next_release_usd: 0,
          ceiling_usd: 750,
          desired_jobs: 4,
          affordable_jobs: 4,
          planned_jobs: 4,
          planned_reserved_usd: 50.4,
          projected_usd: 137.13,
          can_launch_planned: true,
        },
      },
    };

    vi.spyOn(operationsApi, "getPaperMarkdownJobs").mockResolvedValue(monitor);
    renderWithClient(
      <CronJobCard
        job={{ ...job, job_name: "paper_markdown_backfill" }}
        expanded
        onToggle={() => undefined}
      />,
    );

    expect(await screen.findByText("Rolling 30-day window")).toBeInTheDocument();
    expect(screen.getAllByText("Unmetered HF")).toHaveLength(2);
    expect(screen.getByText("Live GPU policy:").parentElement).toHaveTextContent("unmetered on HF · 1 of 1 planned");
    expect(screen.getByText("All history · no automatic reset")).toBeInTheDocument();
    expect(screen.getByText("live-v1").parentElement).toHaveTextContent("max 50 papers · hard 6.0h · soft 5.5h");
    expect(screen.getByText("Logical shard health:").parentElement).toHaveTextContent("6 logical shards / 7 provider attempts · 1 recovered mount failures · 0 unresolved");
    expect(screen.getAllByText("Next admission")).toHaveLength(2);
    expect(screen.getAllByText(/monetary admission is disabled/i)).toHaveLength(2);
    expect(
      screen.getByText(/unresolved image references omitted after final retry/),
    ).toHaveTextContent("2 unresolved image references omitted after final retry");
  });
});

describe("CronSnapshotNotice", () => {
  const snapshot = (overrides: Partial<CronJobsResponse> = {}): CronJobsResponse => ({
    timestamp: "2026-08-14T12:00:00Z",
    jobs: [],
    manual_operations: [],
    summary: {
      total_jobs: 0,
      scheduled_jobs: 0,
      manual_jobs: 0,
      healthy: 0,
      degraded: 0,
      broken: 0,
      running: 0,
      stuck: 0,
      unknown: 0,
      health_score: 100,
      critical_issues: [],
      what_to_check_next: "All monitored jobs look healthy",
      coverage: {
        registered_scheduled_duties: 0,
        discovered_scheduled_duties: 0,
        monitored_duties: 0,
        coverage_gaps: 0,
        gap_ids: [],
      },
    },
    snapshot_generated_at: "2026-08-14T11:58:59Z",
    snapshot_age_seconds: 61,
    snapshot_stale: true,
    refreshing: true,
    ...overrides,
  });

  it("shows stale data while a refresh runs", () => {
    render(<CronSnapshotNotice data={snapshot()} />);
    expect(screen.getByRole("status")).toHaveTextContent("61 seconds old");
  });

  it("stays hidden for a fresh snapshot", () => {
    render(<CronSnapshotNotice data={snapshot({ snapshot_stale: false })} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("polls without hammering the API until the replacement snapshot is fresh", () => {
    expect(cronStatusRefetchInterval(snapshot(), false)).toBe(5000);
    expect(
      cronStatusRefetchInterval(
        snapshot({ snapshot_stale: false, refreshing: false }),
        true,
      ),
    ).toBe(30000);
    expect(
      cronStatusRefetchInterval(
        snapshot({ snapshot_stale: false, refreshing: false }),
        false,
      ),
    ).toBe(false);
  });

  it("uses the forced endpoint for a manual status refresh", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(snapshot()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await operationsApi.getCronStatus(true);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/cron/status?force_refresh=true",
    );
  });
});

describe("CronDashboard refresh controls", () => {
  it("keeps the manual refresh button enabled during an automatic refetch", async () => {
    const freshSnapshot: CronJobsResponse = {
      timestamp: "2026-08-14T12:00:00Z",
      jobs: [],
      manual_operations: [],
      summary: {
        total_jobs: 0,
        scheduled_jobs: 0,
        manual_jobs: 0,
        healthy: 0,
        degraded: 0,
        broken: 0,
        running: 0,
        stuck: 0,
        unknown: 0,
        health_score: 100,
        critical_issues: [],
        what_to_check_next: "All monitored jobs look healthy",
        coverage: {
          registered_scheduled_duties: 0,
          discovered_scheduled_duties: 0,
          monitored_duties: 0,
          coverage_gaps: 0,
          gap_ids: [],
        },
      },
      snapshot_generated_at: "2026-08-14T12:00:00Z",
      snapshot_age_seconds: 0,
      snapshot_stale: false,
      refreshing: false,
    };
    let finishAutomaticRefetch: ((value: CronJobsResponse) => void) | undefined;
    const cronStatus = vi
      .spyOn(operationsApi, "getCronStatus")
      .mockResolvedValueOnce(freshSnapshot)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishAutomaticRefetch = resolve;
          }),
      );
    vi.spyOn(operationsApi, "getPaperMarkdownJobs").mockResolvedValue({
      available: true,
      namespace: "huggingface",
      jobs: [],
      summary: {},
      budgets: {},
    });
    vi.spyOn(chatApi, "getSandboxSpend").mockResolvedValue(status());
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <CronDashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const refreshButton = await screen.findByRole("button", { name: "Refresh" });
    await waitFor(() => expect(refreshButton).toBeEnabled());

    act(() => {
      void queryClient.refetchQueries({ queryKey: ["admin", "cronStatus"] });
    });
    await waitFor(() => expect(cronStatus).toHaveBeenCalledTimes(2));

    expect(refreshButton).toBeEnabled();

    finishAutomaticRefetch?.(freshSnapshot);
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    queryClient.clear();
  });

  it("forces a fresh CRON snapshot and refetches the other admin panels", async () => {
    const snapshot = ({
      timestamp: "2026-08-14T12:00:00Z",
      jobs: [],
      manual_operations: [],
      summary: {
        total_jobs: 0, scheduled_jobs: 0, manual_jobs: 0,
        healthy: 0, degraded: 0, broken: 0, running: 0, stuck: 0, unknown: 0,
        health_score: 100,
        critical_issues: [],
        what_to_check_next: "All monitored jobs look healthy",
        coverage: {
          registered_scheduled_duties: 0, discovered_scheduled_duties: 0,
          monitored_duties: 0, coverage_gaps: 0, gap_ids: [],
        },
      },
      snapshot_generated_at: "2026-08-14T12:00:00Z",
      snapshot_age_seconds: 0,
      snapshot_stale: false,
      refreshing: false,
    } satisfies CronJobsResponse);
    const cronStatus = vi.spyOn(operationsApi, "getCronStatus").mockResolvedValue(snapshot);
    const spend = vi.spyOn(chatApi, "getSandboxSpend").mockResolvedValue(status());
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <CronDashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const refreshButton = await screen.findByRole("button", { name: "Refresh" });
    await waitFor(() => expect(refreshButton).toBeEnabled());
    expect(cronStatus).toHaveBeenCalledTimes(1);
    expect(spend).toHaveBeenCalledTimes(1);

    fireEvent.click(refreshButton);

    await waitFor(() => expect(cronStatus).toHaveBeenLastCalledWith(true));
    await waitFor(() => expect(spend).toHaveBeenCalledTimes(2));
    expect(cronStatus).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(refreshButton).toBeEnabled());

    // A forced refresh is not absorbed by an auto refresh already in flight.
    cronStatus.mockImplementationOnce(() => new Promise(() => {}));
    void queryClient.refetchQueries({ queryKey: ["admin", "cronStatus"] });
    await waitFor(() => expect(cronStatus).toHaveBeenCalledTimes(3));
    fireEvent.click(refreshButton);
    await waitFor(() => expect(cronStatus).toHaveBeenCalledTimes(4));
    expect(cronStatus).toHaveBeenLastCalledWith(true);
    queryClient.clear();
  });
});
