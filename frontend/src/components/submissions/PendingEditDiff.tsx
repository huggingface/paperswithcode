import type React from "react";

import { catalogApi } from "@/lib/api/catalog";
import type { PendingPaperEdit } from "@/lib/pendingEdits";
import { EntitySetDiff, OrganizationSetDiff } from "./diffs/EntitySetDiff";
import { EvaluationsDiff } from "./diffs/EvaluationsDiff";
import { HfArtifactsDiff, ResourceDiff, SourceUrlDiff, XThreadsDiff } from "./diffs/ResourceDiffs";
import { RawJsonToggle } from "./diffs/shared";
import {
  ExternalPaperSuggestionDiff,
  OrganizationSuggestionDiff,
  TaxonomySuggestionDiff,
} from "./diffs/SuggestionDiffs";

function assertNever(value: never): never {
  throw new Error(`Unhandled pending edit: ${JSON.stringify(value)}`);
}

function EditContent({ edit }: { edit: PendingPaperEdit }): React.ReactElement {
  switch (edit.edit_type) {
    case "tasks":
      return <EntitySetDiff
        currentItems={edit.current_payload?.tasks ?? []}
        proposedIds={edit.proposed_payload.task_ids}
        queryPrefix="task"
        fetchEntity={(id) => catalogApi.getTask(id)}
      />;
    case "methods":
      return <EntitySetDiff
        currentItems={edit.current_payload?.methods ?? []}
        proposedIds={edit.proposed_payload.method_ids}
        queryPrefix="method"
        fetchEntity={(id) => catalogApi.getMethod(id)}
      />;
    case "organizations":
      return <OrganizationSetDiff
        currentItems={edit.current_payload?.organizations ?? []}
        proposedIds={edit.proposed_payload.organization_ids}
      />;
    case "repositories":
      return <ResourceDiff
        label="repositories"
        currentItems={edit.current_payload?.repositories ?? []}
        proposedItems={edit.proposed_payload.repositories}
      />;
    case "project_pages":
      return <ResourceDiff
        label="project pages"
        currentItems={edit.current_payload?.project_pages ?? []}
        proposedItems={edit.proposed_payload.project_pages}
      />;
    case "evaluations":
      return <EvaluationsDiff edit={edit} />;
    case "source_url":
      return <SourceUrlDiff edit={edit} />;
    case "hf_artifacts":
      return <HfArtifactsDiff edit={edit} />;
    case "x_threads":
      return <XThreadsDiff edit={edit} />;
    case "new_task":
    case "new_method":
    case "new_benchmark":
    case "new_metric":
    case "new_conference":
      return <TaxonomySuggestionDiff edit={edit} />;
    case "new_organization":
      return <OrganizationSuggestionDiff edit={edit} />;
    case "new_external_paper":
      return <ExternalPaperSuggestionDiff edit={edit} />;
    default:
      return assertNever(edit);
  }
}

function PendingEditDiff({ edit }: { edit: PendingPaperEdit }) {
  return (
    <div className="submission-diff-body">
      <EditContent edit={edit} />
      <RawJsonToggle
        currentPayload={edit.current_payload}
        proposedPayload={edit.proposed_payload}
      />
    </div>
  );
}

export default PendingEditDiff;
