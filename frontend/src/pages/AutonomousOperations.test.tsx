import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { operationsApi, type AutonomousOperationsResponse } from "@/lib/api/operations";
import AutonomousOperations from "./AutonomousOperations";

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: { username: "owner", is_admin: true } }),
}));

const snapshot = (state: AutonomousOperationsResponse["display_state"] = "manual"): AutonomousOperationsResponse => ({
  revision: 7,
  manual_mode: state === "manual",
  monitoring_active: true,
  display_state: state,
  operators: [
    { operator: "submissions", enabled: true, status: "healthy", monitoring_active: true, next_scheduled_run: "2026-08-28T13:00:00Z" },
    { operator: "curation", enabled: false, status: "degraded", monitoring_active: false, next_scheduled_run: null },
    { operator: "cron_health", enabled: true, status: "repairing", monitoring_active: true, next_scheduled_run: null },
    { operator: "chat_reliability", enabled: false, status: "degraded", monitoring_active: false, next_scheduled_run: null },
  ],
  active_lease: { lease_id: "lease", owner_run_id: "run", owner_operator: "cron_health", expires_at: "2026-08-28T13:00:00Z" },
  costs: { input_tokens: 100, output_tokens: 20, total_usd: "0.125000000" },
  baseline: null,
  provider_states: [{ environment: "production", manifest_revision: "provider-v1", state_revision: 2, active_provider: "primary", reason_code: "healthy", updated_at: "2026-08-28T12:00:00Z" }],
  recent_runs: [{ run_id: "run", operator: "cron_health", dry_run: false, status: "completed", exit_classification: "completed", input_tokens: 100, output_tokens: 20, cost_usd: "0.125000000", created_at: "2026-08-28T12:00:00Z" }],
  recent_actions: [{ action_id: "action", run_id: "run", operator: "cron_health", capability: "retry_declared_cron", reason_code: "recovered", resource_kind: "declared_cron", resource_identifier: "refresh_papers", created_at: "2026-08-28T12:00:00Z" }],
  exclusions: ["task_creation", "method_creation", "benchmark_dataset_creation", "metric_creation", "conference_creation"],
});

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><AutonomousOperations /></MemoryRouter></QueryClientProvider>);
};

describe("AutonomousOperations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it.each(["healthy", "degraded", "repairing", "rolled-back", "manual"] as const)("renders %s state", async (state) => {
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(snapshot(state));
    renderPage();
    expect(await screen.findByText(state, { selector: ".text-2xl" })).toBeInTheDocument();
  });

  it("keeps monitoring and hard boundaries visible in manual mode without content", async () => {
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(snapshot());
    renderPage();
    expect(await screen.findByText("Manual mode is enabled.")).toBeInTheDocument();
    expect(screen.getByText(/Monitoring remains active/)).toBeInTheDocument();
    expect(screen.getByText("task_creation")).toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toContain("user chat");
    expect(document.body.textContent?.toLowerCase()).not.toContain("prompt");
  });

  it("allows additional operator shutdowns while manual mode blocks re-enablement", async () => {
    const current = snapshot();
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(current);
    const mutation = vi.spyOn(operationsApi, "setAutonomousOperator").mockResolvedValue({ ...current, revision: 8 });
    renderPage();
    await screen.findByText("Autonomous operations");

    const submissionConfirmation = screen.getByLabelText("Submission review confirmation");
    const disableSubmission = screen.getAllByRole("button", { name: "Disable" })[0];
    fireEvent.change(submissionConfirmation, { target: { value: "SET_OPERATOR_STATE" } });
    expect(disableSubmission).toBeEnabled();
    fireEvent.click(disableSubmission);
    await waitFor(() => expect(mutation).toHaveBeenCalledWith("submissions", false, 7, "SET_OPERATOR_STATE"));

    fireEvent.change(screen.getByLabelText("Chat reliability confirmation"), { target: { value: "SET_OPERATOR_STATE" } });
    for (const enableButton of screen.getAllByRole("button", { name: "Enable" })) {
      expect(enableButton).toBeDisabled();
    }
  });

  it("sends revisioned, typed control mutations through the API client", async () => {
    const current = snapshot("healthy");
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(current);
    const mutation = vi.spyOn(operationsApi, "setAutonomousOperator").mockResolvedValue({ ...current, revision: 8 });
    renderPage();
    await screen.findByText("Autonomous operations");
    const confirmation = screen.getByLabelText("Submission review confirmation");
    expect(screen.getAllByRole("button", { name: "Disable" })[0]).toBeDisabled();
    fireEvent.change(confirmation, { target: { value: "SET_OPERATOR_STATE" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Disable" })[0]);
    await waitFor(() => expect(mutation).toHaveBeenCalledWith("submissions", false, 7, "SET_OPERATOR_STATE"));
  });

  it("requires and forwards typed manual-mode and baseline confirmations", async () => {
    const current = snapshot("healthy");
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(current);
    const manual = vi.spyOn(operationsApi, "setAutonomousManualMode").mockResolvedValue({ ...current, revision: 8, manual_mode: true });
    const baseline = vi.spyOn(operationsApi, "qualifyAutonomousChatBaseline").mockResolvedValue(current);
    renderPage();
    await screen.findByText("Autonomous operations");

    const manualButton = screen.getByRole("button", { name: "Enable manual mode" });
    expect(manualButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Manual mode confirmation"), { target: { value: "SET_MANUAL_MODE" } });
    fireEvent.click(manualButton);
    await waitFor(() => expect(manual).toHaveBeenCalledWith(true, 7, "SET_MANUAL_MODE"));

    fireEvent.change(screen.getByLabelText("Exact baseline SHA"), { target: { value: "a".repeat(40) } });
    const baselineButton = screen.getByRole("button", { name: "Qualify exact SHA" });
    expect(baselineButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Baseline confirmation"), { target: { value: "QUALIFY_CHAT_BASELINE" } });
    fireEvent.click(baselineButton);
    await waitFor(() => expect(baseline).toHaveBeenCalledWith("a".repeat(40), 0, "QUALIFY_CHAT_BASELINE"));
  });

  it("shows stale control failures and asks the operator to refresh", async () => {
    vi.spyOn(operationsApi, "getAutonomousOperations").mockResolvedValue(snapshot("healthy"));
    vi.spyOn(operationsApi, "setAutonomousManualMode").mockRejectedValue(new Error("stale revision (409)"));
    renderPage();
    await screen.findByText("Autonomous operations");
    fireEvent.change(screen.getByLabelText("Manual mode confirmation"), { target: { value: "SET_MANUAL_MODE" } });
    fireEvent.click(screen.getByRole("button", { name: "Enable manual mode" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh before retrying");
  });
});
