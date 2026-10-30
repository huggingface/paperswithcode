import { Fragment } from "react";

import type { Evaluation } from "@/lib/api/evaluations.types";
import type { Paper } from "@/lib/api/papers.types";
import type { PaperEditSection } from "@/lib/paperCuration";

import { EditEvaluationsDialog } from "./EditEvaluationsDialog";
import { EditHfArtifactsDialog } from "./EditHfArtifactsDialog";
import { EditOrganizationsDialog } from "./EditOrganizationsDialog";
import { EditProjectPagesDialog } from "./EditProjectPagesDialog";
import { EditRepositoriesDialog } from "./EditRepositoriesDialog";
import { EditSourceUrlDialog } from "./EditSourceUrlDialog";
import { EditTaxonomyTagsDialog } from "./EditTaxonomyTagsDialog";
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
    paperId: paper.id,
    arxivId,
    submitMode: editSubmitMode,
    isAuthor: isLinkedAuthor,
    onOpenChange: (open: boolean) => onOpenChange(activeEditor, open),
  };
  const officialUrls = (items?: Array<{ url: string; is_official?: boolean | null }>) =>
    items?.map(({ url, is_official }) => ({ url, is_official: Boolean(is_official) })) ?? [];

  const editors: EditorRegistry = {
    tasks: () => <EditTaxonomyTagsDialog {...shared} kind="task" initialItems={paper.tasks ?? []} />,
    methods: () => <EditTaxonomyTagsDialog {...shared} kind="method" initialItems={paper.methods ?? []} />,
    repositories: () => (
      <EditRepositoriesDialog {...shared} initialRepositories={officialUrls(paper.repositories)} />
    ),
    project_pages: () => (
      <EditProjectPagesDialog {...shared} initialProjectPages={officialUrls(paper.project_pages)} />
    ),
    evaluations: () => (
      <EditEvaluationsDialog
        {...shared}
        initialEvaluations={evaluations}
        paperTasks={paper.tasks ?? []}
        isAdmin={isAdmin}
      />
    ),
    source_url: () => (
      <EditSourceUrlDialog {...shared} initialUrl={paper.source_url ?? paper.url_abs ?? ""} />
    ),
    hf_artifacts: () => (
      <EditHfArtifactsDialog
        {...shared}
        initialArtifacts={{
          hf_models: paper.hf_models ?? [],
          hf_datasets: paper.hf_datasets ?? [],
          hf_spaces: paper.hf_spaces ?? [],
        }}
      />
    ),
    x_threads: () => (
      <EditXThreadsDialog {...shared} initialUrls={paper.x_threads?.map(({ url }) => url) ?? []} />
    ),
    organizations: () => (
      <EditOrganizationsDialog
        {...shared}
        initialOrganizationIds={(paper.organizations ?? []).map(({ id }) => Number(id))}
      />
    ),
  };

  // Keyed so switching editors never carries one editor's draft into another.
  return <Fragment key={activeEditor}>{editors[activeEditor]()}</Fragment>;
}
