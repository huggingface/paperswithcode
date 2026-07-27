import React from "react";
import { useQueries } from "@tanstack/react-query";

import { cn } from "@/lib/utils";
import {
  getDataset,
  getMethod,
  getTask,
  type Dataset,
  type Method,
  type PendingEditType,
  type Task,
} from "@/lib/api";
import { assetUrl } from "@/lib/apiUrl";

type JsonRecord = Record<string, unknown>;

interface PendingEditDiffProps {
  editType: PendingEditType;
  currentPayload?: JsonRecord | null;
  proposedPayload: JsonRecord;
}

interface NamedItem {
  id: number;
  name: string;
  slug?: string;
}

interface UrlItem {
  url: string;
  is_official: boolean;
}

interface EvaluationLike {
  id?: number;
  task_id?: number;
  dataset_id?: number;
  model_name?: string | null;
  harness?: string | null;
  methodology?: string | null;
  metrics?: Record<string, string | number>;
  uses_additional_data?: boolean;
  is_open?: boolean;
  best_rank?: number | null;
  best_metric?: string | null;
  evaluated_on?: string | null;
  external_source_url?: string | null;
  num_parameters?: number | null;
  hf_model_url?: string | null;
}

interface EvaluationOperation {
  op?: string;
  evaluation_id?: number;
  data?: EvaluationLike;
}

const asRecord = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};

const asNamedItems = (value: unknown): NamedItem[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const record = asRecord(item);
      const id = Number(record.id);
      if (!Number.isFinite(id)) return null;
      return {
        id,
        name: typeof record.name === "string" ? record.name : `#${id}`,
        slug: typeof record.slug === "string" ? record.slug : undefined,
      };
    })
    .filter((item): item is NamedItem => Boolean(item));
};

const asNumberArray = (value: unknown): number[] => {
  if (!Array.isArray(value)) return [];
  return value.map(Number).filter((id) => Number.isFinite(id));
};

const asUrlItems = (value: unknown): UrlItem[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const record = asRecord(item);
      if (typeof record.url !== "string") return null;
      return {
        url: record.url,
        is_official: Boolean(record.is_official),
      };
    })
    .filter((item): item is UrlItem => Boolean(item));
};

const asEvaluations = (value: unknown): EvaluationLike[] => {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asRecord(item) as EvaluationLike);
};

const asOperations = (value: unknown): EvaluationOperation[] => {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asRecord(item) as EvaluationOperation);
};

const formatEditType = (type: PendingEditType): string => type.replace(/_/g, " ");

function RawJsonToggle({ currentPayload, proposedPayload }: Omit<PendingEditDiffProps, "editType">) {
  const [showRaw, setShowRaw] = React.useState(false);
  return (
    <div className="submission-raw-toggle">
      <button
        type="button"
        className="raw-json-btn"
        onClick={() => setShowRaw((value) => !value)}
      >
        {showRaw ? "Hide raw JSON" : "Show raw JSON"}
      </button>
      {showRaw && (
        <div className="submission-json-grid">
          <JsonBlock title="Current payload" value={currentPayload ?? {}} />
          <JsonBlock title="Proposed payload" value={proposedPayload} />
        </div>
      )}
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="submission-json-block">
      <div className="submission-diff-label">{title}</div>
      <pre>
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function EntitySetDiff({
  currentItems,
  proposedIds,
  queryPrefix,
  fetchEntity,
}: {
  currentItems: NamedItem[];
  proposedIds: number[];
  queryPrefix: "task" | "method";
  fetchEntity: (id: string) => Promise<Task | Method>;
}) {
  const ids = React.useMemo(
    () => Array.from(new Set([...currentItems.map((item) => item.id), ...proposedIds])).sort((a, b) => a - b),
    [currentItems, proposedIds],
  );

  const entityQueries = useQueries({
    queries: ids.map((id) => ({
      queryKey: [queryPrefix, String(id)],
      queryFn: () => fetchEntity(String(id)),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const namesById = React.useMemo(() => {
    const map = new Map<number, string>();
    currentItems.forEach((item) => map.set(item.id, item.name));
    entityQueries.forEach((query) => {
      const entity = query.data;
      if (!entity) return;
      const id = Number(entity.id);
      if (Number.isFinite(id)) {
        map.set(id, entity.name);
      }
    });
    return map;
  }, [currentItems, entityQueries]);

  const currentIds = new Set(currentItems.map((item) => item.id));
  const proposedIdSet = new Set(proposedIds);
  const removedIds = ids.filter((id) => currentIds.has(id) && !proposedIdSet.has(id));
  const addedIds = ids.filter((id) => !currentIds.has(id) && proposedIdSet.has(id));

  const renderPill = (id: number, mode: "current" | "proposed") => {
    const isRemoved = mode === "current" && removedIds.includes(id);
    const isAdded = mode === "proposed" && addedIds.includes(id);
    return (
      <span
        key={id}
        className={cn(
          "submission-diff-pill",
          isRemoved && "removed",
          isAdded && "added",
        )}
      >
        {namesById.get(id) ?? `#${id}`}
      </span>
    );
  };

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

function ResourceDiff({ label, currentItems, proposedItems }: {
  label: string;
  currentItems: UrlItem[];
  proposedItems: UrlItem[];
}) {
  const currentByUrl = new Map(currentItems.map((item) => [item.url, item]));
  const proposedByUrl = new Map(proposedItems.map((item) => [item.url, item]));
  const urls = Array.from(new Set([...currentByUrl.keys(), ...proposedByUrl.keys()])).sort();

  if (urls.length === 0) {
    return <EmptyInline>No {label} in this submission.</EmptyInline>;
  }

  return (
    <div className="submission-url-list">
      {urls.map((url) => {
        const current = currentByUrl.get(url);
        const proposed = proposedByUrl.get(url);
        const added = !current && proposed;
        const removed = current && !proposed;
        const officialChanged =
          current && proposed && current.is_official !== proposed.is_official;

        return (
          <div
            key={url}
            className={cn(
              "submission-url-row",
              added && "added",
              removed && "removed",
              officialChanged && "changed",
            )}
          >
            <div className="submission-url-content">
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn("submission-url-link", removed && "removed")}
              >
                {url}
              </a>
              {added && <span className="submission-pill status approved">Added</span>}
              {removed && <span className="submission-pill status rejected">Removed</span>}
              {officialChanged && (
                <span className="submission-pill changed">
                  Official: {String(current.is_official)} {"->"} {String(proposed.is_official)}
                </span>
              )}
              {(proposed ?? current)?.is_official && <span className="submission-pill">Official</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EvaluationsDiff({
  currentPayload,
  proposedPayload,
}: {
  currentPayload?: JsonRecord | null;
  proposedPayload: JsonRecord;
}) {
  const currentEvaluations = asEvaluations(asRecord(currentPayload).evaluations);
  const operations = asOperations(proposedPayload.operations);

  const taskIds = React.useMemo(() => {
    const ids = new Set<number>();
    currentEvaluations.forEach((evaluation) => {
      if (evaluation.task_id) ids.add(Number(evaluation.task_id));
    });
    operations.forEach((operation) => {
      const data = operation.data;
      if (data?.task_id) ids.add(Number(data.task_id));
    });
    return Array.from(ids).filter((id) => Number.isFinite(id));
  }, [currentEvaluations, operations]);

  const datasetIds = React.useMemo(() => {
    const ids = new Set<number>();
    currentEvaluations.forEach((evaluation) => {
      if (evaluation.dataset_id) ids.add(Number(evaluation.dataset_id));
    });
    operations.forEach((operation) => {
      const data = operation.data;
      if (data?.dataset_id) ids.add(Number(data.dataset_id));
    });
    return Array.from(ids).filter((id) => Number.isFinite(id));
  }, [currentEvaluations, operations]);

  const taskQueries = useQueries({
    queries: taskIds.map((id) => ({
      queryKey: ["task", String(id)],
      queryFn: () => getTask(String(id)),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const datasetQueries = useQueries({
    queries: datasetIds.map((id) => ({
      queryKey: ["dataset", String(id)],
      queryFn: () => getDataset(String(id)),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const taskNames = React.useMemo(() => {
    const map = new Map<number, string>();
    taskQueries.forEach((query) => {
      const task = query.data;
      if (!task) return;
      const id = Number(task.id);
      if (Number.isFinite(id)) map.set(id, task.name);
    });
    return map;
  }, [taskQueries]);

  const datasetNames = React.useMemo(() => {
    const map = new Map<number, string>();
    datasetQueries.forEach((query) => {
      const dataset = query.data as Dataset | undefined;
      if (!dataset) return;
      const id = Number(dataset.id);
      if (Number.isFinite(id)) map.set(id, dataset.name);
    });
    return map;
  }, [datasetQueries]);

  const currentById = new Map(
    currentEvaluations
      .filter((evaluation) => evaluation.id != null)
      .map((evaluation) => [Number(evaluation.id), evaluation]),
  );

  if (operations.length === 0) {
    return <EmptyInline>No evaluation operations in this payload.</EmptyInline>;
  }

  return (
    <div className="submission-eval-list">
      {operations.map((operation, index) => {
        const current = operation.evaluation_id ? currentById.get(operation.evaluation_id) : undefined;
        const merged = operation.op === "update" ? { ...current, ...operation.data } : operation.data ?? current;
        const fields = merged ?? {};
        return (
          <div key={`${operation.op}-${operation.evaluation_id ?? index}`} className="submission-eval-op">
            <div className="submission-eval-op-header">
              <span
                className={cn(
                  "submission-pill status",
                  operation.op === "create" && "approved",
                  operation.op === "update" && "changed",
                  operation.op === "delete" && "rejected",
                )}
              >
                {operation.op ?? "unknown"}
              </span>
              {operation.evaluation_id && (
                <span className="submission-meta">Evaluation #{operation.evaluation_id}</span>
              )}
            </div>
            {operation.op && ["create", "update", "delete"].includes(operation.op) ? (
              <EvaluationFields
                evaluation={fields}
                taskNames={taskNames}
                datasetNames={datasetNames}
              />
            ) : (
              <JsonBlock title="Unsupported operation" value={operation} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function EvaluationFields({
  evaluation,
  taskNames,
  datasetNames,
}: {
  evaluation: EvaluationLike;
  taskNames: Map<number, string>;
  datasetNames: Map<number, string>;
}) {
  const taskId = evaluation.task_id ? Number(evaluation.task_id) : undefined;
  const datasetId = evaluation.dataset_id ? Number(evaluation.dataset_id) : undefined;
  const metrics = evaluation.metrics ?? {};

  return (
    <div className="submission-eval-fields">
      <Field label="Task" value={taskId ? taskNames.get(taskId) ?? `#${taskId}` : null} />
      <Field label="Dataset" value={datasetId ? datasetNames.get(datasetId) ?? `#${datasetId}` : null} />
      <Field label="Model" value={evaluation.model_name || null} />
      <Field label="Harness" value={evaluation.harness || null} />
      <Field label="Best rank" value={evaluation.best_rank ?? null} />
      <Field label="Parameters" value={evaluation.num_parameters ?? null} />
      <Field label="HF model URL" value={evaluation.hf_model_url || null} />
      <Field
        label="Open source"
        value={
          evaluation.is_open === undefined
            ? null
            : evaluation.is_open
              ? "Yes"
              : "No"
        }
      />
      <div className="submission-eval-metrics">
        <div className="submission-diff-label">Metrics</div>
        {Object.keys(metrics).length > 0 ? (
          <div className="submission-metric-list">
            {Object.entries(metrics).map(([name, value]) => (
              <span key={name} className="submission-metric-pill">
                {name}: {String(value)}
              </span>
            ))}
          </div>
        ) : (
          <EmptyInline>No metrics</EmptyInline>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="submission-diff-label">{label}</div>
      <div className="submission-field-value">{value ?? <span className="submission-muted">Not set</span>}</div>
    </div>
  );
}

function SourceUrlDiff({ currentPayload, proposedPayload }: {
  currentPayload?: JsonRecord | null;
  proposedPayload: JsonRecord;
}) {
  const currentUrl = asRecord(currentPayload).source_url;
  const proposedUrl = proposedPayload.source_url;

  return (
    <div className="submission-diff-columns">
      <DiffColumn title="Current source URL">
        {typeof currentUrl === "string" && currentUrl ? (
          <a className="submission-url-link" href={currentUrl} target="_blank" rel="noopener noreferrer">
            {currentUrl}
          </a>
        ) : (
          <EmptyInline>No current URL</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Proposed source URL">
        {typeof proposedUrl === "string" && proposedUrl ? (
          <a className="submission-url-link" href={proposedUrl} target="_blank" rel="noopener noreferrer">
            {proposedUrl}
          </a>
        ) : (
          <EmptyInline>No proposed URL</EmptyInline>
        )}
      </DiffColumn>
    </div>
  );
}

function TaxonomySuggestionDiff({
  kind,
  proposedPayload,
}: {
  kind: "task" | "method" | "benchmark" | "metric" | "conference";
  proposedPayload: JsonRecord;
}) {
  const name = typeof proposedPayload.name === "string" ? proposedPayload.name : "";
  const description =
    typeof proposedPayload.description === "string" ? proposedPayload.description : "";
  const dates = typeof proposedPayload.dates === "string" ? proposedPayload.dates : "";
  const venue = typeof proposedPayload.venue === "string" ? proposedPayload.venue : "";
  const url = typeof proposedPayload.url === "string" ? proposedPayload.url : "";
  const image = asRecord(proposedPayload.image);
  const imageDataUrl =
    typeof image.data_url === "string" && image.data_url.startsWith("data:image/")
      ? image.data_url
      : "";
  const imageUrl =
    typeof image.url === "string" ? assetUrl(image.url) ?? "" : imageDataUrl;
  const imageFileName =
    typeof image.file_name === "string" ? image.file_name : "Suggested image";
  const imageCredit =
    typeof proposedPayload.image_credit === "string" ? proposedPayload.image_credit : "";
  const source = typeof proposedPayload.source === "string" ? proposedPayload.source : "";

  return (
    <div className="submission-diff-columns">
      <DiffColumn title={`Suggested ${kind} name`}>
        {name ? (
          <span className="submission-diff-pill added">{name}</span>
        ) : (
          <EmptyInline>No name provided</EmptyInline>
        )}
      </DiffColumn>
      <DiffColumn title="Description">
        {description ? (
          <span className="submission-field-value">{description}</span>
        ) : (
          <EmptyInline>No description provided</EmptyInline>
        )}
      </DiffColumn>
      {(kind === "task" || kind === "method") && (
        <>
          <DiffColumn title="Image">
            {imageUrl ? (
              <img
                src={imageUrl}
                alt={imageFileName}
                className="max-h-64 max-w-full rounded-md border border-border object-contain"
              />
            ) : (
              <EmptyInline>No image provided</EmptyInline>
            )}
          </DiffColumn>
          <DiffColumn title="Image source">
            {imageCredit || <EmptyInline>No image source provided</EmptyInline>}
          </DiffColumn>
        </>
      )}
      {kind === "method" && (
        <DiffColumn title="Source">
          {source ? (
            source.startsWith("http://") || source.startsWith("https://") ? (
              <a
                className="submission-url-link"
                href={source}
                target="_blank"
                rel="noopener noreferrer"
              >
                {source}
              </a>
            ) : (
              <span className="submission-field-value">{source}</span>
            )
          ) : (
            <EmptyInline>No source provided</EmptyInline>
          )}
        </DiffColumn>
      )}
      {kind === "conference" && (
        <>
          <DiffColumn title="Dates">
            {dates || <EmptyInline>No dates provided</EmptyInline>}
          </DiffColumn>
          <DiffColumn title="Venue">
            {venue || <EmptyInline>No venue provided</EmptyInline>}
          </DiffColumn>
          <DiffColumn title="URL">
            {url ? (
              <a
                className="submission-url-link"
                href={url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {url}
              </a>
            ) : (
              <EmptyInline>No URL provided</EmptyInline>
            )}
          </DiffColumn>
        </>
      )}
    </div>
  );
}

function DiffColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="submission-diff-column">
      <div className="submission-diff-label">{title}</div>
      <div className="submission-diff-pills">{children}</div>
    </div>
  );
}

function EmptyInline({ children }: { children: React.ReactNode }) {
  return <span className="submission-muted">{children}</span>;
}

function HfArtifactsDiff({
  currentPayload,
  proposedPayload,
}: {
  currentPayload?: JsonRecord | null;
  proposedPayload: JsonRecord;
}) {
  const current = asRecord(currentPayload);
  const sections = [
    { key: "hf_models", label: "Models" },
    { key: "hf_datasets", label: "Datasets" },
    { key: "hf_spaces", label: "Spaces" },
  ] as const;

  return (
    <div className="submission-hf-artifacts-diff">
      {sections.map(({ key, label }) => {
        const currentUrls = Array.isArray(current[key])
          ? (current[key] as unknown[]).filter((item): item is string => typeof item === "string")
          : [];
        const proposedUrls = Array.isArray(proposedPayload[key])
          ? (proposedPayload[key] as unknown[]).filter((item): item is string => typeof item === "string")
          : [];

        return (
          <div key={key} className="submission-hf-artifacts-section">
            <div className="submission-diff-label">{label}</div>
            <ResourceDiff
              label={label.toLowerCase()}
              currentItems={currentUrls.map((url) => ({ url, is_official: false }))}
              proposedItems={proposedUrls.map((url) => ({ url, is_official: false }))}
            />
          </div>
        );
      })}
    </div>
  );
}

export function PendingEditDiff({ editType, currentPayload, proposedPayload }: PendingEditDiffProps) {
  const current = asRecord(currentPayload);

  let content: React.ReactNode;
  if (editType === "tasks") {
    content = (
      <EntitySetDiff
        currentItems={asNamedItems(current.tasks)}
        proposedIds={asNumberArray(proposedPayload.task_ids)}
        queryPrefix="task"
        fetchEntity={getTask}
      />
    );
  } else if (editType === "methods") {
    content = (
      <EntitySetDiff
        currentItems={asNamedItems(current.methods)}
        proposedIds={asNumberArray(proposedPayload.method_ids)}
        queryPrefix="method"
        fetchEntity={getMethod}
      />
    );
  } else if (editType === "repositories") {
    content = (
      <ResourceDiff
        label="repositories"
        currentItems={asUrlItems(current.repositories)}
        proposedItems={asUrlItems(proposedPayload.repositories)}
      />
    );
  } else if (editType === "project_pages") {
    content = (
      <ResourceDiff
        label="project pages"
        currentItems={asUrlItems(current.project_pages)}
        proposedItems={asUrlItems(proposedPayload.project_pages)}
      />
    );
  } else if (editType === "evaluations") {
    content = <EvaluationsDiff currentPayload={currentPayload} proposedPayload={proposedPayload} />;
  } else if (editType === "source_url") {
    content = <SourceUrlDiff currentPayload={currentPayload} proposedPayload={proposedPayload} />;
  } else if (editType === "hf_artifacts") {
    content = <HfArtifactsDiff currentPayload={currentPayload} proposedPayload={proposedPayload} />;
  } else if (editType === "new_task") {
    content = <TaxonomySuggestionDiff kind="task" proposedPayload={proposedPayload} />;
  } else if (editType === "new_method") {
    content = <TaxonomySuggestionDiff kind="method" proposedPayload={proposedPayload} />;
  } else if (editType === "new_benchmark") {
    content = <TaxonomySuggestionDiff kind="benchmark" proposedPayload={proposedPayload} />;
  } else if (editType === "new_metric") {
    content = <TaxonomySuggestionDiff kind="metric" proposedPayload={proposedPayload} />;
  } else if (editType === "new_conference") {
    content = <TaxonomySuggestionDiff kind="conference" proposedPayload={proposedPayload} />;
  } else {
    content = (
      <div className="submission-empty submission-empty-warn">
        No custom renderer exists yet for {formatEditType(editType)}.
      </div>
    );
  }

  return (
    <div className="submission-diff-body">
      {content}
      <RawJsonToggle currentPayload={currentPayload} proposedPayload={proposedPayload} />
    </div>
  );
}

export default PendingEditDiff;
