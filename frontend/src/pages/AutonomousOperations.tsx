import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowLeft, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import "./CronDashboard.css";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { operationsApi, type AutonomousOperationsResponse } from "@/lib/api/operations";
import { formatCronDate, toneClass, type Tone } from "@/lib/cronStatus";
import { adminQueryKeys } from "@/lib/api/queryKeys";

const labels: Record<string, string> = {
  submissions: "Submission review",
  curation: "Scheduled curation",
  cron_health: "CRON health",
  chat_reliability: "Chat reliability",
};

const stateTones: Record<AutonomousOperationsResponse["display_state"], Tone> = {
  healthy: "healthy",
  degraded: "degraded",
  repairing: "running",
  "rolled-back": "broken",
  manual: "degraded",
};

const AutonomousOperations = () => {
  const queryClient = useQueryClient();
  const [baselineSha, setBaselineSha] = useState("");
  const [manualConfirmation, setManualConfirmation] = useState("");
  const [operatorConfirmations, setOperatorConfirmations] = useState<Record<string, string>>({});
  const [baselineConfirmation, setBaselineConfirmation] = useState("");
  const query = useQuery({
    queryKey: adminQueryKeys.autonomousOperations,
    queryFn: () => operationsApi.getAutonomousOperations(),
    refetchInterval: 30_000,
    retry: false,
  });
  const update = useMutation({
    mutationFn: (operation: () => Promise<AutonomousOperationsResponse>) => operation(),
    onSuccess: (data) => {
      queryClient.setQueryData(adminQueryKeys.autonomousOperations, data);
      setManualConfirmation("");
      setOperatorConfirmations({});
      setBaselineConfirmation("");
    },
  });
  const data = query.data;
  const mutationError = update.error instanceof Error ? update.error.message : null;

  if (query.isLoading) {
    return <div className="page" aria-busy="true">Loading autonomous operations…</div>;
  }
  if (query.error || !data) {
    return <div className="page"><h1>Autonomous operations unavailable</h1><p>{query.error instanceof Error ? query.error.message : "No status was returned."}</p></div>;
  }

  const setManualMode = () => update.mutate(() =>
    operationsApi.setAutonomousManualMode(!data.manual_mode, data.revision, manualConfirmation));
  const setOperator = (operator: string, enabled: boolean) => update.mutate(() =>
    operationsApi.setAutonomousOperator(operator, enabled, data.revision, operatorConfirmations[operator] ?? ""));
  const qualifyBaseline = () => {
    const expectedRevision = data.baseline?.revision ?? 0;
    update.mutate(() => operationsApi.qualifyAutonomousChatBaseline(baselineSha, expectedRevision, baselineConfirmation));
  };

  return (
    <div className="cron-dashboard" data-shadcn>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3"><Activity className="h-8 w-8" />Autonomous operations</h1>
            <p className="mt-2 cron-muted">Content-free supervision, remote controls, and bounded audit history.</p>
          </div>
          <Button asChild variant="outline"><Link to="/admin-dashboard"><ArrowLeft className="h-4 w-4 mr-2" />Admin dashboard</Link></Button>
        </div>

        {data.manual_mode && (
          <Card className="cron-status--degraded" role="status">
            <CardContent className="pt-6 flex gap-3"><ShieldAlert className="h-5 w-5" /><div><strong>Manual mode is enabled.</strong><p>{data.monitoring_active ? "Monitoring remains active" : "Monitoring is not currently verified"}; autonomous callbacks, retries, deployments, and data mutations fail closed.</p></div></CardContent>
          </Card>
        )}

        <div className="grid md:grid-cols-4 gap-4">
          <Card className={toneClass(stateTones[data.display_state])}><CardHeader><CardTitle className="text-sm">Overall state</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold capitalize">{data.display_state}</div><p className="text-sm">Monitoring {data.monitoring_active ? "active" : "inactive"}</p></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Codex cost</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">${data.costs.total_usd}</div><p className="text-sm">{data.costs.input_tokens + data.costs.output_tokens} tokens</p></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Repair lease</CardTitle></CardHeader><CardContent><div className="text-lg font-bold">{data.active_lease ? data.active_lease.owner_operator : "Available"}</div><p className="text-sm">{data.active_lease ? `Expires ${formatCronDate(data.active_lease.expires_at)}` : "No active source repair"}</p></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Global control</CardTitle></CardHeader><CardContent className="space-y-2"><Input aria-label="Manual mode confirmation" value={manualConfirmation} onChange={(event) => setManualConfirmation(event.target.value)} placeholder="Type SET_MANUAL_MODE" /><Button disabled={update.isPending || manualConfirmation !== "SET_MANUAL_MODE"} onClick={setManualMode}>{data.manual_mode ? "Leave manual mode" : "Enable manual mode"}</Button></CardContent></Card>
        </div>

        <div className="grid md:grid-cols-4 gap-4">
          {data.operators.map((operator) => (
            <Card key={operator.operator} className={toneClass(stateTones[operator.status])}>
              <CardHeader><CardTitle className="flex justify-between gap-2"><span>{labels[operator.operator]}</span><Badge>{operator.status}</Badge></CardTitle></CardHeader>
              <CardContent className="space-y-3"><p>{operator.enabled ? "Mutation enabled" : "Mutation disabled"} · monitoring {operator.monitoring_active ? "active" : "unverified"}</p><p className="text-sm">Next scheduled run: {operator.next_scheduled_run ? formatCronDate(operator.next_scheduled_run) : "not scheduled"}</p><Input aria-label={`${labels[operator.operator]} confirmation`} value={operatorConfirmations[operator.operator] ?? ""} onChange={(event) => setOperatorConfirmations((current) => ({ ...current, [operator.operator]: event.target.value }))} placeholder="Type SET_OPERATOR_STATE" /><Button disabled={update.isPending || (data.manual_mode && !operator.enabled) || operatorConfirmations[operator.operator] !== "SET_OPERATOR_STATE"} onClick={() => setOperator(operator.operator, !operator.enabled)}>{operator.enabled ? "Disable" : "Enable"}</Button></CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader><CardTitle>Qualified scalable-chat baseline</CardTitle></CardHeader>
          <CardContent className="space-y-3"><p className="font-mono break-all">{data.baseline?.sha ?? "No baseline qualified"}</p>{data.baseline && <p className="text-sm">Revision {data.baseline.revision} · {data.baseline.qualified_by} · {formatCronDate(data.baseline.qualified_at)}</p>}<div className="grid md:grid-cols-[1fr_1fr_auto] gap-2"><Input aria-label="Exact baseline SHA" value={baselineSha} onChange={(event) => setBaselineSha(event.target.value)} placeholder="40-character lowercase commit SHA" /><Input aria-label="Baseline confirmation" value={baselineConfirmation} onChange={(event) => setBaselineConfirmation(event.target.value)} placeholder="Type QUALIFY_CHAT_BASELINE" /><Button disabled={update.isPending || !/^[0-9a-f]{40}$/.test(baselineSha) || baselineConfirmation !== "QUALIFY_CHAT_BASELINE"} onClick={qualifyBaseline}>Qualify exact SHA</Button></div></CardContent>
        </Card>

        <Card><CardHeader><CardTitle>Provider and fallback state</CardTitle></CardHeader><CardContent>{data.provider_states.length ? <ul className="space-y-2">{data.provider_states.map((provider) => <li key={provider.environment}><strong>{provider.environment}</strong>: {provider.active_provider} · {provider.reason_code} · manifest {provider.manifest_revision}</li>)}</ul> : <p>No provider state recorded.</p>}</CardContent></Card>

        <div className="grid md:grid-cols-2 gap-4">
          <Card><CardHeader><CardTitle>Recent runs</CardTitle></CardHeader><CardContent>{data.recent_runs.length ? <ul className="space-y-2">{data.recent_runs.map((run) => <li key={run.run_id}><strong>{labels[run.operator]}</strong> · {run.status} · {run.exit_classification} · ${run.cost_usd} · {formatCronDate(run.created_at)}</li>)}</ul> : <p>No runs recorded.</p>}</CardContent></Card>
          <Card><CardHeader><CardTitle>Recent actions</CardTitle></CardHeader><CardContent>{data.recent_actions.length ? <ul className="space-y-2">{data.recent_actions.map((action) => <li key={action.action_id}><strong>{labels[action.operator]}</strong> · {action.capability} · {action.reason_code} · {action.resource_kind}/{action.resource_identifier}</li>)}</ul> : <p>No actions recorded.</p>}</CardContent></Card>
        </div>

        <Card><CardHeader><CardTitle>Hard exclusions</CardTitle></CardHeader><CardContent><ul className="list-disc pl-5">{data.exclusions.map((exclusion) => <li key={exclusion}>{exclusion}</li>)}</ul></CardContent></Card>
        {mutationError && <p role="alert">Control update failed: {mutationError}. Refresh before retrying.</p>}
      </div>
    </div>
  );
};

export default AutonomousOperations;
