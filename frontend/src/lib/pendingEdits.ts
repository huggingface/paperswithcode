import { z } from "zod";

const record = z.record(z.unknown());
const namedItem = z.object({
  id: z.number(),
  name: z.string(),
  slug: z.string().optional(),
}).passthrough();
const urlItem = z.object({ url: z.string(), is_official: z.boolean() });
const evaluationData = z.object({
  task_id: z.number(),
  dataset_id: z.number(),
  model_name: z.string().nullish(),
  harness: z.string().nullish(),
  methodology: z.string().nullish(),
  metrics: z.record(z.union([z.string(), z.number()])),
  uses_additional_data: z.boolean().optional(),
  is_open: z.boolean().optional(),
  best_rank: z.number().nullish(),
  best_metric: z.string().nullish(),
  evaluated_on: z.string().nullish(),
  external_source_url: z.string().nullish(),
  num_parameters: z.number().nullish(),
  hf_model_url: z.string().nullish(),
}).passthrough();
const evaluationSnapshot = evaluationData.partial().extend({ id: z.number().optional() });
const evaluationOperation = z.discriminatedUnion("op", [
  z.object({ op: z.literal("create"), data: evaluationData }),
  z.object({ op: z.literal("update"), evaluation_id: z.number(), data: evaluationData }),
  z.object({ op: z.literal("delete"), evaluation_id: z.number() }),
]);

const artifactsPayload = z.object({
  hf_models: z.array(z.string()),
  hf_datasets: z.array(z.string()),
  hf_spaces: z.array(z.string()),
});
const suggestionImage = z.object({
  file_name: z.string(),
  mime_type: z.string(),
  data_url: z.string().optional(),
  url: z.string().optional(),
});
const suggestionBase = z.object({
  name: z.string(),
  description: z.string().optional(),
});
const newTaskPayload = suggestionBase.extend({
  image: suggestionImage.optional(),
  image_credit: z.string().optional(),
  parent_id: z.number().optional(),
  area_id: z.number().optional(),
  keywords: z.string().optional(),
});
const newMethodPayload = suggestionBase.extend({
  image: suggestionImage.optional(),
  image_credit: z.string().optional(),
  source_paper_id: z.number().optional(),
  source_url: z.string().optional(),
  source_title: z.string().optional(),
});
const newBenchmarkPayload = suggestionBase.extend({
  description: z.string(),
  task_ids: z.array(z.number()),
  full_name: z.string().optional(),
  url: z.string().optional(),
  hf_url: z.string().optional(),
  paper_url: z.string().optional(),
  license_name: z.string().optional(),
  license_url: z.string().optional(),
});
const newMetricPayload = suggestionBase.extend({
  description: z.string(),
  direction: z.enum(["higher_is_better", "lower_is_better"]),
  full_name: z.string().optional(),
  scale: z.string().optional(),
  task_id: z.number(),
  dataset_id: z.number(),
});
const newConferencePayload = suggestionBase.extend({
  short_name: z.string().optional(),
  venue: z.string().optional(),
  location: z.string().optional(),
  url: z.string(),
  year: z.number(),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
});

const base = z.object({
  id: z.number(),
  paper_id: z.number().nullable(),
  hf_username: z.string(),
  is_author: z.boolean(),
  status: z.enum(["pending", "approved", "rejected"]),
  applied_payload: record.nullish(),
  conflict_payload: record.nullish(),
  result_entity_type: z.string().nullish(),
  result_entity_id: z.string().nullish(),
  admin_note: z.string().nullish(),
  user_review_reason: z.string().nullish(),
  reviewed_by: z.string().nullish(),
  reviewed_by_kind: z.enum(["human", "codex"]).nullish(),
  review_evidence: record.nullish(),
  created_at: z.string(),
  updated_at: z.string(),
  reviewed_at: z.string().nullish(),
});

function variant<Type extends string, Payload extends z.ZodTypeAny, Current extends z.ZodTypeAny>(
  editType: Type,
  proposedPayload: Payload,
  currentPayload: Current,
) {
  return base.extend({
    edit_type: z.literal(editType),
    proposed_payload: proposedPayload,
    current_payload: currentPayload.nullish(),
  });
}

const taskEdit = variant(
  "tasks",
  z.object({ task_ids: z.array(z.number()) }),
  z.object({ tasks: z.array(namedItem) }),
);
const methodEdit = variant(
  "methods",
  z.object({ method_ids: z.array(z.number()) }),
  z.object({ methods: z.array(namedItem) }),
);
const evaluationEdit = variant(
  "evaluations",
  z.object({ operations: z.array(evaluationOperation) }),
  z.object({ evaluations: z.array(evaluationSnapshot) }),
);
const repositoryEdit = variant(
  "repositories",
  z.object({ repositories: z.array(urlItem) }),
  z.object({ repositories: z.array(urlItem) }),
);
const projectPageEdit = variant(
  "project_pages",
  z.object({ project_pages: z.array(urlItem) }),
  z.object({ project_pages: z.array(urlItem) }),
);
const sourceUrlEdit = variant(
  "source_url",
  z.object({ source_url: z.string() }),
  z.object({ source_url: z.string().nullish() }),
);
const hfArtifactsEdit = variant("hf_artifacts", artifactsPayload, artifactsPayload);
const organizationEdit = variant(
  "organizations",
  z.object({ organization_ids: z.array(z.number()) }),
  z.object({ organizations: z.array(namedItem) }),
);
const newTask = variant("new_task", newTaskPayload, record);
const newMethod = variant("new_method", newMethodPayload, record);
const newBenchmark = variant("new_benchmark", newBenchmarkPayload, record);
const newMetric = variant("new_metric", newMetricPayload, record);
const newConference = variant("new_conference", newConferencePayload, record);
const newExternalPaper = variant(
  "new_external_paper",
  z.object({
    title: z.string().optional(),
    source_url: z.string(),
    authors: z.array(z.string()),
    date_published: z.string().optional(),
    abstract: z.string().optional(),
  }),
  record,
);

const pendingPaperEditSchema = z.discriminatedUnion("edit_type", [
  taskEdit,
  methodEdit,
  evaluationEdit,
  repositoryEdit,
  projectPageEdit,
  sourceUrlEdit,
  hfArtifactsEdit,
  organizationEdit,
  newTask,
  newMethod,
  newBenchmark,
  newMetric,
  newConference,
  newExternalPaper,
]);

export type PendingPaperEdit = z.infer<typeof pendingPaperEditSchema>;
export type PendingEditType = PendingPaperEdit["edit_type"];
export type PendingEditStatus = PendingPaperEdit["status"];
export type PendingPaperEditSubmitPayload = PendingPaperEdit extends infer Edit
  ? Edit extends PendingPaperEdit
    ? Pick<Edit, "paper_id" | "edit_type" | "proposed_payload">
    : never
  : never;

type EditOf<Type extends PendingEditType> = Extract<PendingPaperEdit, { edit_type: Type }>;

export function pendingEditSubmission<Type extends PendingEditType>(
  paperId: number | null,
  editType: Type,
  proposedPayload: EditOf<Type>["proposed_payload"],
): Pick<EditOf<Type>, "paper_id" | "edit_type" | "proposed_payload"> {
  return {
    paper_id: paperId,
    edit_type: editType,
    proposed_payload: proposedPayload,
  } as Pick<EditOf<Type>, "paper_id" | "edit_type" | "proposed_payload">;
}

export interface PendingPaperEditsResponse {
  count: number;
  results: PendingPaperEdit[];
}

const responseSchema = z.object({
  count: z.number(),
  results: z.array(pendingPaperEditSchema),
});

export class PendingEditPayloadError extends Error {
  constructor(message: string) {
    super(`Malformed pending-edit payload: ${message}`);
    this.name = "PendingEditPayloadError";
  }
}

function parse<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (result.success) return result.data;
  const issue = result.error.issues[0];
  throw new PendingEditPayloadError(
    `${issue?.path.join(".") || "response"}: ${issue?.message || "invalid value"}`,
  );
}

export const parsePendingPaperEdit = (value: unknown): PendingPaperEdit =>
  parse(pendingPaperEditSchema, value);

export const parsePendingPaperEditsResponse = (value: unknown): PendingPaperEditsResponse =>
  parse(responseSchema, value);
