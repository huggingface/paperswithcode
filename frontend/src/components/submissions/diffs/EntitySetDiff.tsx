import React from "react";
import { useQueries, useQuery } from "@tanstack/react-query";

import { cn } from "@/lib/utils";
import type { Method, Task } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import type { NamedItem } from "@/lib/pendingEdits";
import { DiffColumn, EmptyInline } from "./shared";
import { catalogQueryKeys } from "@/lib/api/queryKeys";

export function EntitySetDiff({
  currentItems,
  proposedIds,
  queryPrefix,
  fetchEntity,
  knownNames,
}: {
  currentItems: NamedItem[];
  proposedIds: number[];
  queryPrefix: "task" | "method" | "organization";
  fetchEntity?: (id: string) => Promise<Task | Method>;
  knownNames?: Map<number, string>;
}) {
  const ids = React.useMemo(
    () => Array.from(new Set([...currentItems.map((item) => item.id), ...proposedIds])).sort((a, b) => a - b),
    [currentItems, proposedIds],
  );

  const entityQueries = useQueries({
    queries: fetchEntity ? ids.map((id) => ({
      queryKey: catalogQueryKeys[queryPrefix](String(id)),
      queryFn: () => fetchEntity(String(id)),
      staleTime: 5 * 60 * 1000,
    })) : [],
  });

  const namesById = React.useMemo(() => {
    const map = new Map<number, string>();
    currentItems.forEach((item) => map.set(item.id, item.name));
    knownNames?.forEach((name, id) => map.set(id, name));
    entityQueries.forEach(({ data }) => {
      if (data) map.set(Number(data.id), data.name);
    });
    return map;
  }, [currentItems, entityQueries, knownNames]);

  const currentIds = new Set(currentItems.map((item) => item.id));
  const proposedIdSet = new Set(proposedIds);

  const renderPill = (id: number, mode: "current" | "proposed") => (
    <span
      key={id}
      className={cn(
        "submission-diff-pill",
        mode === "current" && !proposedIdSet.has(id) && "removed",
        mode === "proposed" && !currentIds.has(id) && "added",
      )}
    >
      {namesById.get(id) ?? `#${id}`}
    </span>
  );

  return (
    <div className="submission-diff-columns">
      <DiffColumn title="Currently tagged">
        {currentItems.length > 0 ? (
          currentItems.map((item) => renderPill(item.id, "current"))
        ) : (
          <EmptyInline>No current tags</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Will be tagged">
        {proposedIds.length > 0 ? (
          proposedIds.map((id) => renderPill(id, "proposed"))
        ) : (
          <EmptyInline>No proposed tags</EmptyInline>
        )}
      </DiffColumn>
    </div>
  );
}

export function OrganizationSetDiff({
  currentItems,
  proposedIds,
}: {
  currentItems: NamedItem[];
  proposedIds: number[];
}) {
  const organizations = useQuery({
    queryKey: [...catalogQueryKeys.organizations, "submission-diff"],
    queryFn: () => catalogApi.organizations(),
    staleTime: 5 * 60 * 1000,
  });
  const names = new Map(currentItems.map((item) => [item.id, item.name]));
  organizations.data?.results.forEach((organization) => {
    names.set(Number(organization.id), organization.name);
  });

  return (
    <EntitySetDiff
      currentItems={currentItems}
      proposedIds={proposedIds}
      queryPrefix="organization"
      knownNames={names}
    />
  );
}
