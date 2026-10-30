import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Paper } from "@/lib/api/papers.types";
import type { PaperEditSection } from "@/lib/paperCuration";
import { PaperDetailEditors } from "./PaperDetailEditors";

vi.mock("./EditTaxonomyTagsDialog", () => ({
  EditTaxonomyTagsDialog: ({ kind }: { kind: string }) => <div>{kind === "task" ? "tasks" : "methods"} editor</div>,
}));
vi.mock("./EditRepositoriesDialog", () => ({ EditRepositoriesDialog: () => <div>repositories editor</div> }));
vi.mock("./EditProjectPagesDialog", () => ({ EditProjectPagesDialog: () => <div>project_pages editor</div> }));
vi.mock("./EditEvaluationsDialog", () => ({ EditEvaluationsDialog: () => <div>evaluations editor</div> }));
vi.mock("./EditSourceUrlDialog", () => ({ EditSourceUrlDialog: () => <div>source_url editor</div> }));
vi.mock("./EditHfArtifactsDialog", () => ({ EditHfArtifactsDialog: () => <div>hf_artifacts editor</div> }));
vi.mock("./EditXThreadsDialog", () => ({ EditXThreadsDialog: () => <div>x_threads editor</div> }));
vi.mock("./EditOrganizationsDialog", () => ({ EditOrganizationsDialog: () => <div>organizations editor</div> }));

const paper: Paper = {
  id: "17",
  arxiv_id: "2608.00123",
  url_abs: "https://arxiv.org/abs/2608.00123",
  url_pdf: null,
  title: "Paper",
  abstract: "Abstract",
  authors: ["Author"],
  published: "2026-08-01",
  version: "v1",
  is_latest_version: true,
  citation_count: 0,
};

describe("PaperDetailEditors", () => {
  it.each([
    "tasks",
    "methods",
    "repositories",
    "project_pages",
    "evaluations",
    "source_url",
    "hf_artifacts",
    "x_threads",
    "organizations",
  ] satisfies PaperEditSection[])("renders the registered %s editor", (activeEditor) => {
    render(
      <PaperDetailEditors
        activeEditor={activeEditor}
        arxivId="2608.00123"
        editSubmitMode="pending"
        evaluations={[]}
        isAdmin={false}
        isLinkedAuthor={false}
        onOpenChange={vi.fn()}
        paper={paper}
      />,
    );

    expect(screen.getByText(`${activeEditor} editor`)).toBeInTheDocument();
  });
});
