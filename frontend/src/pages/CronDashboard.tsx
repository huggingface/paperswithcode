import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Clock,
  XCircle,
  Loader2,
  Activity,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { CronJobCard } from "@/components/cron/CronJobCard";
import { CodexJobQueue } from "@/components/admin/CodexJobQueue";
import { CatalogAuditPanel } from "@/components/admin/CatalogAuditPanel";
import { chatApi, type ChatSandboxSpendStatus, type ChatWebSearchBudgetStatus } from "@/lib/api/chat";
import { operationsApi, type CronJobHealth, type CronJobsResponse, type CronJobStatus } from "@/lib/api/operations";
import { ApiError } from "@/lib/apiTransport";
import { formatCronDate, formatMicroUsd as usd, toneClass, type Tone } from "@/lib/cronStatus";
import { useAuth } from "@/lib/authContext";
import { isStagingEnvironment } from "@/lib/apiUrl";
import "./CronDashboard.css";
import { adminQueryKeys } from "@/lib/api/queryKeys";

const categoryTones: Record<string, Tone> = {
  hourly: "running",
  daily: "healthy",
  weekly: "degraded",
  systemd: "running",
};

export const ChatComputePanel = ({ data, loading, error }: {
  data?: ChatSandboxSpendStatus;
  loading: boolean;
  error: unknown;
}) => {
  const [policyProfile, setPolicyProfile] = useState("staging-current");
  const policyProfiles: Record<string, string> = {
    "staging-current": "Starter staging · $75 warning / $100 trip / no Environment cap",
    "staging-production-era": "Staging with production · $15 / $20 / $25",
    production: "Production · $175 / $200 / $225",
  };
  if (loading) {
    return <div className="flex items-center py-12"><Loader2 className="h-6 w-6 animate-spin mr-3" />Loading chat compute…</div>;
  }
  if (error || !data) {
    return <Card className="cron-status--broken"><CardContent className="pt-6">Chat compute accounting is unavailable.</CardContent></Card>;
  }
  const percent = Math.min(100, data.effective_microusd / data.application_cap_microusd * 100);
  const stateLabel = data.circuit_state === "tripped" ? "Chat disabled" : data.circuit_state === "warning" ? "Operator warning" : "Enabled";
  const reconciliationLabel = data.reconciliation_state === "fresh" ? "Fresh" : data.reconciliation_state === "stale" ? "Stale" : "Unavailable";
  return <div className="space-y-6">
    <div className="grid md:grid-cols-4 gap-4">
      <Card className={data.circuit_state === "tripped" ? "cron-status--broken" : data.circuit_state === "warning" ? "cron-status--degraded" : ""}><CardHeader><CardTitle className="text-sm">Circuit</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stateLabel}</div><p className="text-xs cron-muted">{data.trip_reason ?? "Policy armed"}</p></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Month to date</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{usd(data.effective_microusd)}</div><div role="progressbar" aria-label="Application cap used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)} className="h-2 rounded bg-muted mt-3"><div className="h-2 rounded bg-primary" style={{ width: `${percent}%` }} /></div></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Application headroom</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{usd(data.remaining_microusd)}</div><p className="text-xs cron-muted">Cap {usd(data.application_cap_microusd)}</p></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-sm">Live compute</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{data.live_count}</div><p className="text-xs cron-muted">{data.termination_uncertain_count} termination uncertain</p></CardContent></Card>
    </div>
    <Card><CardHeader><CardTitle>Accounting and policy</CardTitle><CardDescription>{data.environment} · cycle {data.billing_cycle}</CardDescription></CardHeader><CardContent className="grid md:grid-cols-3 gap-4 text-sm">
      <div><strong>Environment record</strong><br />{data.environment} · {data.provider_mode === "starter_workspace" ? "Starter Workspace" : "Team isolated"}</div>
      <label><strong>Policy profile</strong><select aria-label="Chat compute policy profile" value={policyProfile} onChange={(event) => setPolicyProfile(event.target.value)} className="block mt-1"><option value="staging-current">Staging now</option><option value="staging-production-era">Staging with production</option><option value="production">Production</option></select><span className="text-xs cron-muted">{policyProfiles[policyProfile]} · Workspace $250</span></label>
      <div><strong>Conservative estimate</strong><br />{usd(data.estimated_microusd)}</div>
      <div><strong>Provider-reported floor</strong><br />{usd(data.provider_floor_microusd)} · <Badge>{reconciliationLabel}</Badge></div>
      <div><strong>Provider backstops</strong><br />{data.environment_cap_microusd === null ? "Starter: no Environment cap" : `Environment ${usd(data.environment_cap_microusd)}`} · Workspace {usd(data.workspace_cap_microusd)}</div>
      <div><strong>Active thresholds</strong><br />Warning {usd(data.warning_microusd)} · trip {usd(data.application_cap_microusd)}</div>
      <div><strong>Policy allocation</strong><br />Starter staging $75/$100 with no Environment cap · future Team staging $15/$20/$25 · production $175/$200/$225 · workspace $250</div>
      <div><strong>Cycle end</strong><br />{formatCronDate(data.cycle_end_at)}</div>
      <div><strong>Last metered</strong><br />{data.last_metered_at ? formatCronDate(data.last_metered_at) : "Unavailable"}</div>
      <div><strong>Provider reconciliation</strong><br />{data.last_reconciled_at ? formatCronDate(data.last_reconciled_at) : "Unavailable"}{data.last_reconciliation_attempt_at ? ` · attempted ${formatCronDate(data.last_reconciliation_attempt_at)}` : ""}{data.next_reconciliation_at ? ` · next ${formatCronDate(data.next_reconciliation_at)}` : ""}</div>
      <div><strong>Burn projection</strong><br />{data.burn_rate_microusd_per_hour === null ? "Not enough data" : `${usd(data.burn_rate_microusd_per_hour)}/hour${data.projected_cap_hit_at ? ` · cap ${formatCronDate(data.projected_cap_hit_at)}` : ""}`}</div>
      <div><strong>Prior cycle</strong><br />{data.prior_cycle ? `${data.prior_cycle.billing_cycle} · ${usd(data.prior_cycle.effective_microusd)}` : "Not enough data"}</div>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Live lifecycle</CardTitle></CardHeader><CardContent className="text-sm">{Object.entries(data.live_states).map(([state, count]) => <span className="mr-4" key={state}>{state}: {count}</span>)}</CardContent></Card>
    <Card><CardHeader><CardTitle>Daily spend</CardTitle></CardHeader><CardContent>{data.daily_spend.length ? <ul className="space-y-1 text-sm">{data.daily_spend.map((day) => <li key={day.date}>{day.date}: blank {usd(day.blank_pool_microusd)} · assigned {usd(day.assigned_microusd)}</li>)}</ul> : <p className="cron-muted">No compute recorded in this cycle.</p>}</CardContent></Card>
    <Card><CardHeader><CardTitle>Recent circuit events</CardTitle><CardDescription>Runbook: docs/chat-sandbox-spend-runbook.md</CardDescription></CardHeader><CardContent>{data.events.length ? <ul className="space-y-2 text-sm">{data.events.map((event) => <li key={event.id}><Badge>{event.severity}</Badge> {event.type} · {formatCronDate(event.created_at)}</li>)}</ul> : <p className="cron-muted">No events in this cycle.</p>}</CardContent></Card>
  </div>;
};

const WebSearchBudgetPanel = ({ data, loading, error }: {
  data?: ChatWebSearchBudgetStatus;
  loading: boolean;
  error: unknown;
}) => {
  if (loading) return <div className="flex items-center py-8"><Loader2 className="h-5 w-5 animate-spin mr-3" />Loading web-search budget…</div>;
  if (error || !data) return <Card className="cron-status--broken"><CardContent className="pt-6">Web-search budget accounting is unavailable.</CardContent></Card>;
  const percent = Math.min(100, data.call_count / data.hard_limit_calls * 100);
  return <Card className={data.circuit_state === "tripped" ? "cron-status--broken" : data.circuit_state === "warning" || data.circuit_state === "cooldown" ? "cron-status--degraded" : ""}>
    <CardHeader><CardTitle>Web search</CardTitle><CardDescription>{data.environment} · UTC cycle {data.billing_cycle} · provider details are admin-only</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      <div className="grid md:grid-cols-4 gap-4 text-sm">
        <div><strong>Circuit</strong><br />{data.circuit_state}{data.trip_reason ? ` · ${data.trip_reason}` : ""}</div>
        <div><strong>Calls</strong><br />{data.call_count} / {data.hard_limit_calls} · {data.success_count} successful</div>
        <div><strong>Remaining</strong><br />{data.remaining_calls}</div>
        <div><strong>Warning</strong><br />{data.warning_calls} calls</div>
      </div>
      <div role="progressbar" aria-label="Web-search monthly budget used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)} className="h-2 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${percent}%` }} /></div>
      <p className="text-xs cron-muted">Cycle ends {formatCronDate(data.cycle_end_at)} · provider-reported cost ${(data.provider_cost_microusd / 1_000_000).toFixed(4)}{data.last_latency_ms !== null ? ` · last ${data.last_latency_ms} ms / ${data.last_result_count ?? 0} results` : ""}{data.cooldown_until ? ` · cooldown until ${formatCronDate(data.cooldown_until)}` : ""}{data.last_provider_error_class ? ` · last provider error ${data.last_provider_error_class}` : ""}</p>
      {data.events.length > 0 && <ul className="space-y-1 text-sm">{data.events.map((event) => <li key={event.id}>{event.type} · {formatCronDate(event.created_at)}{event.error_class ? ` · ${event.error_class}` : ""}</li>)}</ul>}
    </CardContent>
  </Card>;
};

export const CronSnapshotNotice = ({ data }: { data?: CronJobsResponse }) => {
  if (!data?.snapshot_stale) return null;
  return (
    <Card className="mb-6 cron-status--degraded" role="status">
      <CardContent className="pt-6">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>
            Refreshing status… Current snapshot is {Math.ceil(data.snapshot_age_seconds)} seconds old.
          </span>
        </div>
      </CardContent>
    </Card>
  );
};

export const cronStatusRefetchInterval = (
  data: CronJobsResponse | undefined,
  autoRefresh: boolean,
) => {
  if (data?.snapshot_stale || data?.refreshing) return 5000;
  return autoRefresh ? 30000 : false;
};

const CronDashboard = () => {
  const staging = isStagingEnvironment();
  const queryClient = useQueryClient();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [chatEnvironmentDraft, setChatEnvironmentDraft] = useState("");
  const [chatEnvironment, setChatEnvironment] = useState("");
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const { user } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: adminQueryKeys.cronStatus,
    queryFn: () => operationsApi.getCronStatus(),
    refetchInterval: (query) => cronStatusRefetchInterval(query.state.data, autoRefresh),
    retry: false,
  });
  const chatSpendQuery = useQuery({
    queryKey: adminQueryKeys.chatSandboxSpend(chatEnvironment),
    queryFn: () => chatApi.getSandboxSpend(chatEnvironment || undefined),
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });
  const webSearchBudgetQuery = useQuery({
    queryKey: adminQueryKeys.chatWebSearchBudget,
    queryFn: () => chatApi.getWebSearchBudget(),
    enabled: staging,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });
  // Force a fresh CRON snapshot and refetch every other admin panel on screen.
  const refresh = useMutation({
    mutationFn: () => Promise.all([
      // Cancel an in-flight auto refresh so it cannot absorb the forced fetch.
      queryClient.cancelQueries({ queryKey: adminQueryKeys.cronStatus }).then(() =>
        queryClient.fetchQuery({
          queryKey: adminQueryKeys.cronStatus,
          queryFn: () => operationsApi.getCronStatus(true),
          retry: false,
        })),
      queryClient.refetchQueries({
        queryKey: adminQueryKeys.all,
        type: "active",
        predicate: (query) => query.queryKey[1] !== adminQueryKeys.cronStatus[1],
      }),
    ]),
  });

  const errorMessage = error instanceof ApiError && error.status === 401
    ? "Unauthorized. Sign in with an allowlisted Hugging Face admin account."
    : error instanceof Error ? error.message : undefined;

  const toggleJobExpansion = (jobName: string) => {
    setExpandedJobs((prev) => {
      const next = new Set(prev);
      if (next.has(jobName)) next.delete(jobName);
      else next.add(jobName);
      return next;
    });
  };

  const leaderboardSyncJobs = data?.jobs.filter(
    (job) => job.dashboard_group === "leaderboard_sync",
  ) ?? [];
  const scheduledJobs = data?.jobs.filter(
    (job) => job.category !== "manual" && job.dashboard_group !== "leaderboard_sync",
  ) ?? [];
  const criticalJobs = scheduledJobs.filter((job) => job.critical);
  const otherJobs = scheduledJobs.filter((job) => !job.critical);
  const manualOperations = data?.manual_operations ?? [];
  const refreshButtonBusy = Boolean(
    isLoading || refresh.isPending || data?.refreshing,
  );

  const jobsByCategory = otherJobs.reduce((acc, job) => {
    if (!acc[job.category]) acc[job.category] = [];
    acc[job.category].push(job);
    return acc;
  }, {} as Record<string, CronJobStatus[]>);

  const sortedCategories = Object.keys(jobsByCategory).sort((a, b) => {
    const order = ["systemd", "hourly", "daily", "weekly", "backfill"];
    return order.indexOf(a) - order.indexOf(b);
  });

  const renderJobCard = (job: CronJobStatus) => (
    <CronJobCard
      key={job.job_name}
      job={job}
      expanded={expandedJobs.has(job.job_name)}
      onToggle={() => toggleJobExpansion(job.job_name)}
      autoRefresh={autoRefresh}
    />
  );

  return (
    <div className="cron-dashboard" data-shadcn>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold flex items-center gap-3">
                <Activity className="h-8 w-8 cron-info-text" />
                Admin Dashboard
              </h1>
              <p className="mt-2 cron-muted">
                Paper curation queue and operational health for scheduled jobs
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button asChild variant="outline" size="sm">
                <Link to="/autonomous-operations">Autonomous operations</Link>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={autoRefresh ? "cron-status--running" : ""}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${autoRefresh ? "animate-spin" : ""}`} />
                Auto-refresh {autoRefresh ? "ON" : "OFF"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => refresh.mutate()} disabled={refreshButtonBusy}>
                <RefreshCw className={`h-4 w-4 mr-2 ${refreshButtonBusy ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </div>

        <Card className="mb-6">
          <CardContent className="pt-6">
            <p className="text-sm cron-muted">
              Signed in as <span className="font-semibold">@{user?.username}</span>. Health checks prefer
              database freshness over log completion so silent no-work failures surface as degraded or broken.
              Expanded jobs include deterministic scheduler, log, lock, durable-data, throughput, backlog,
              and semantic contract evidence with direct operator and run links.
            </p>
          </CardContent>
        </Card>

        <CronSnapshotNotice data={data} />

        <Tabs defaultValue="critical-jobs">
          <TabsList className="grid h-auto w-full grid-cols-2 sm:w-auto sm:grid-cols-5">
            <TabsTrigger value="critical-jobs">Critical Jobs</TabsTrigger>
            <TabsTrigger value="leaderboard-syncs">Leaderboard Syncs</TabsTrigger>
            <TabsTrigger value="codex-paper-jobs">Codex Paper Jobs</TabsTrigger>
            <TabsTrigger value="catalog-audit">Catalog Audit</TabsTrigger>
            <TabsTrigger value="chat-compute">Chat Compute</TabsTrigger>
          </TabsList>

          <TabsContent value="critical-jobs" className="mt-6">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin cron-info-text" />
                <span className="ml-3 cron-muted">Loading CRON jobs status...</span>
              </div>
            )}

            {error && (
              <Card className="cron-status--broken">
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-5 w-5" />
                    <p>{errorMessage ?? "Failed to load CRON jobs status. Please try again."}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            {data && (
              <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
              {(["healthy", "degraded", "broken", "running", "stuck", "unknown"] as CronJobHealth[]).map(
                (status) => (
                  <Card key={status}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium cron-muted capitalize">
                        {status}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{data.summary[status]}</div>
                    </CardContent>
                  </Card>
                ),
              )}
            </div>

            {data.summary.critical_issues.length > 0 && (
              <Card className="mb-6 cron-status--broken">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ShieldAlert className="h-5 w-5" />
                    Critical job issues
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="list-disc pl-5 space-y-1 text-sm">
                    {data.summary.critical_issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="text-base">What to check next</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm cron-muted">{data.summary.what_to_check_next}</p>
                <p className="mt-2 text-xs cron-muted flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Last updated: {formatCronDate(data.timestamp)} · Health score:{" "}
                  {data.summary.health_score.toFixed(0)}%
                </p>
              </CardContent>
            </Card>

            <Card className={`mb-8 ${data.summary.coverage.coverage_gaps ? "cron-status--broken" : ""}`}>
              <CardHeader>
                <CardTitle className="text-base">Coverage</CardTitle>
                <CardDescription>Registry and deployed scheduler inventory</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div><span className="cron-label">Registered</span><div className="text-2xl font-bold">{data.summary.coverage.registered_scheduled_duties}</div></div>
                <div><span className="cron-label">Discovered</span><div className="text-2xl font-bold">{data.summary.coverage.discovered_scheduled_duties}</div></div>
                <div><span className="cron-label">Monitored</span><div className="text-2xl font-bold">{data.summary.coverage.monitored_duties}</div></div>
                <div><span className="cron-label">Gaps</span><div className="text-2xl font-bold">{data.summary.coverage.coverage_gaps}</div></div>
              </CardContent>
            </Card>

            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="text-xl">Critical jobs</CardTitle>
                <CardDescription>Writers whose stale output breaks the live site</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {criticalJobs.map(renderJobCard)}
              </CardContent>
            </Card>

            <div className="space-y-6">
              {sortedCategories.map((category) => (
                <Card key={category}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xl capitalize flex items-center gap-2">
                        <Badge className={toneClass(categoryTones[category] ?? categoryTones.hourly)}>
                          {category}
                        </Badge>
                        <span>Supporting jobs</span>
                      </CardTitle>
                      <CardDescription>
                        {jobsByCategory[category].length} job
                        {jobsByCategory[category].length !== 1 ? "s" : ""}
                      </CardDescription>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {jobsByCategory[category].map(renderJobCard)}
                  </CardContent>
                </Card>
              ))}
            </div>

            {manualOperations.length > 0 && (
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle className="text-xl">Manual operations</CardTitle>
                  <CardDescription>Visible invocation history; excluded from scheduled health and coverage</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {manualOperations.map(renderJobCard)}
                </CardContent>
              </Card>
            )}
              </>
            )}
          </TabsContent>

          <TabsContent value="leaderboard-syncs" className="mt-6">
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin cron-info-text" />
                <span className="ml-3 cron-muted">Loading leaderboard sync status...</span>
              </div>
            )}
            {error && (
              <Card className="cron-status--broken">
                <CardContent className="pt-6">
                  <div className="flex items-center gap-3">
                    <XCircle className="h-5 w-5" />
                    <p>{errorMessage ?? "Failed to load leaderboard sync status. Please try again."}</p>
                  </div>
                </CardContent>
              </Card>
            )}
            {data && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <CardTitle className="text-xl">Leaderboard syncs</CardTitle>
                      <CardDescription>
                        Recurring imports from externally maintained benchmark leaderboards
                      </CardDescription>
                    </div>
                    <Badge>{leaderboardSyncJobs.length} jobs</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {leaderboardSyncJobs.map(renderJobCard)}
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="codex-paper-jobs" className="mt-6">
            <CodexJobQueue autoRefresh={autoRefresh} />
          </TabsContent>
          <TabsContent value="catalog-audit" className="mt-6">
            <CatalogAuditPanel />
          </TabsContent>
          <TabsContent value="chat-compute" className="mt-6">
            <Card className="mb-6"><CardHeader><CardTitle>Environment record</CardTitle><CardDescription>Leave blank for live staging, or enter the isolated environment printed by the spend qualification command.</CardDescription></CardHeader><CardContent className="flex gap-2"><input aria-label="Chat compute environment record" value={chatEnvironmentDraft} onChange={(event) => setChatEnvironmentDraft(event.target.value)} placeholder="staging-q-example" className="flex-1 rounded border px-3 py-2" /><Button onClick={() => setChatEnvironment(chatEnvironmentDraft.trim())}>Load</Button></CardContent></Card>
            <ChatComputePanel data={chatSpendQuery.data} loading={chatSpendQuery.isLoading} error={chatSpendQuery.error} />
            {staging && <div className="mt-6"><WebSearchBudgetPanel data={webSearchBudgetQuery.data} loading={webSearchBudgetQuery.isLoading} error={webSearchBudgetQuery.error} /></div>}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default CronDashboard;
