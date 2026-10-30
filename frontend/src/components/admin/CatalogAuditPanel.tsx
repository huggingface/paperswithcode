import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { PaperEditDigest } from "./PaperEditDigest";
import { paperEditsApi } from "@/lib/api/paperEdits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { catalogApi } from "@/lib/api/catalog";
import { adminQueryKeys } from "@/lib/api/queryKeys";

export const CatalogAuditPanel = () => {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: adminQueryKeys.catalogAudit,
    queryFn: ({ pageParam }) => catalogApi.audit(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const events = query.data?.pages.flatMap((page) => page.events) ?? [];
  const refresh = () => queryClient.invalidateQueries({ queryKey: adminQueryKeys.catalogAudit });
  const acknowledge = useMutation({
    mutationFn: () => catalogApi.acknowledgeAudit(),
    onSuccess: refresh,
  });
  const rollback = useMutation({
    mutationFn: (eventId: string) => catalogApi.rollbackEvent(eventId),
    onSuccess: refresh,
  });

  const suspension = useMutation({
    mutationFn: ({ subject, suspended }: { subject: string; suspended: boolean }) => paperEditsApi.suspend(subject, suspended),
    onSuccess: refresh,
  });

  return (
    <div className="space-y-4">
      <PaperEditDigest />
      {(rollback.error || suspension.error) && <p role="alert">{(rollback.error || suspension.error)?.message}</p>}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Catalog mutation audit</CardTitle>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">
              {query.data?.pages[0]?.unread_contributor_count ?? 0} unread contributor changes
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => acknowledge.mutate()}
              disabled={acknowledge.isPending}
            >
              Mark read
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {query.isLoading && <p>Loading audit history…</p>}
          {query.error && <p className="text-destructive">Audit history unavailable.</p>}
          {events.map((event) => (
            <article
              key={event.id}
              className={`rounded-md border p-3 ${
                event.operation === "delete" || event.rollback_eligible === false
                  ? "border-red-500 bg-red-50/50"
                  : ""
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong>
                  {event.operation} {event.entity_type} {event.entity_id}
                </strong>
                <span className="text-xs text-muted-foreground">
                  @{event.actor_username ?? event.actor_role} ·{" "}
                  {new Date(event.created_at).toLocaleString()}
                </span>
              </div>
              <details className="mt-2 text-xs">
                <summary>Inspect snapshots</summary>
                <pre className="mt-2 max-h-80 overflow-auto rounded bg-muted p-3">
                  {JSON.stringify({ before: event.before, after: event.after }, null, 2)}
                </pre>
              </details>
              {event.actor_role === "contributor" && event.actor_hf_subject && <Button className="mt-3 mr-2" variant="outline" size="sm" disabled={suspension.isPending} onClick={() => suspension.mutate({ subject: event.actor_hf_subject!, suspended: !event.editing_suspended })}>
                {event.editing_suspended ? "Restore editing access" : "Suspend editing access"}
              </Button>}
              {!event.rollback_of_event_id && (
                <Button
                  className="mt-3"
                  variant="outline"
                  size="sm"
                  onClick={() => rollback.mutate(event.id)}
                  disabled={rollback.isPending || event.rollback_eligible === false}
                >
                  {event.rollback_eligible === false
                    ? "Rollback conflict"
                    : "Roll back if unchanged"}
                </Button>
              )}
            </article>
          ))}
          {query.hasNextPage && (
            <Button
              variant="outline"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
            >
              {query.isFetchingNextPage ? "Loading…" : "Load older events"}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
