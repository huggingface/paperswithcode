import type { Evaluation } from "@/lib/api/evaluations.types";
import type { Paper } from "@/lib/api/papers.types";
import type { PaperEditSection } from "@/hooks/usePaperEditState";

import { EditEvaluationsDialog } from "./EditEvaluationsDialog";
import { EditHfArtifactsDialog } from "./EditHfArtifactsDialog";
import { EditMethodsDialog } from "./EditMethodsDialog";
import { EditOrganizationsDialog } from "./EditOrganizationsDialog";
import { EditProjectPagesDialog } from "./EditProjectPagesDialog";
import { EditRepositoriesDialog } from "./EditRepositoriesDialog";
import { EditSourceUrlDialog } from "./EditSourceUrlDialog";
import { EditTasksDialog } from "./EditTasksDialog";
import { EditXThreadsDialog } from "./EditXThreadsDialog";

interface PaperDetailEditorsProps {
  activeEditor: PaperEditSection | null;
  arxivId: string;
  editSubmitMode: "direct" | "pending";
  evaluations: Evaluation[];
  isAdmin: boolean;
  isLinkedAuthor: boolean;
  onOpenChange: (section: PaperEditSection, open: boolean) => void;
  paper: Paper;
}

type EditorRegistry = {
  [Section in PaperEditSection]: () => React.ReactNode;
};

export function PaperDetailEditors({
  activeEditor,
  arxivId,
  editSubmitMode,
  evaluations,
  isAdmin,
  isLinkedAuthor,
  onOpenChange,
  paper,
}: PaperDetailEditorsProps) {
  if (!activeEditor) return null;

  const shared = {
    open: true,
    paperId: paper.id,
    arxivId,
    submitMode: editSubmitMode,
    isAuthor: isLinkedAuthor,
  };
  const close = (section: PaperEditSection) => (open: boolean) =>
    onOpenChange(section, open);

  const editors: EditorRegistry = {
    tasks: () => (
      <EditTasksDialog
        {...shared}
        onOpenChange={close("tasks")}
        initialTaskIds={paper.tasks?.map((task) => Number(task.id)) ?? []}
        initialTasks={paper.tasks ?? []}
      />
    ),
    methods: () => (
      <EditMethodsDialog
        {...shared}
        onOpenChange={close("methods")}
        initialMethodIds={paper.methods?.map((method) => Number(method.id)) ?? []}
        initialMethods={paper.methods ?? []}
      />
    ),
    repositories: () => (
      <EditRepositoriesDialog
        {...shared}
        onOpenChange={close("repositories")}
        initialRepositories={paper.repositories?.map(({ url, is_official }) => ({
          url,
          is_official: Boolean(is_official),
        })) ?? []}
      />
    ),
    "project-pages": () => (
      <EditProjectPagesDialog
        {...shared}
        onOpenChange={close("project-pages")}
        initialProjectPages={paper.project_pages?.map(({ url, is_official }) => ({
          url,
          is_official: Boolean(is_official),
        })) ?? []}
      />
    ),
    results: () => (
      <EditEvaluationsDialog
        {...shared}
        onOpenChange={close("results")}
        initialEvaluations={evaluations}
        paperTasks={paper.tasks ?? []}
        isAdmin={isAdmin}
      />
    ),
    "source-url": () => (
      <EditSourceUrlDialog
        {...shared}
        onOpenChange={close("source-url")}
        initialUrl={paper.source_url ?? paper.url_abs ?? ""}
      />
    ),
    "hf-artifacts": () => (
      <EditHfArtifactsDialog
        {...shared}
        onOpenChange={close("hf-artifacts")}
        initialArtifacts={{
          hf_models: paper.hf_models ?? [],
          hf_datasets: paper.hf_datasets ?? [],
          hf_spaces: paper.hf_spaces ?? [],
        }}
      />
    ),
    "x-threads": () => (
      <EditXThreadsDialog
        {...shared}
        onOpenChange={close("x-threads")}
        initialUrls={paper.x_threads?.map(({ url }) => url) ?? []}
      />
    ),
    organizations: () => (
      <EditOrganizationsDialog
        open
        paperId={paper.id}
        onOpenChange={close("organizations")}
        initialOrganizationIds={(paper.organizations ?? []).map(({ id }) => Number(id))}
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
    ),
  };

  return editors[activeEditor]();
}
