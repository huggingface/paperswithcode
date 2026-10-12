import { useCallback, useState } from "react";

export type PaperEditSection =
  | "tasks"
  | "methods"
  | "results"
  | "repositories"
  | "project-pages"
  | "hf-artifacts"
  | "organizations"
  | "source-url"
  | "x-threads";

const FRESH_AUTH_EDIT_SECTIONS: Record<string, PaperEditSection> = {
  tasks: "tasks",
  methods: "methods",
  evaluations: "results",
  repositories: "repositories",
  project_pages: "project-pages",
  hf_artifacts: "hf-artifacts",
  organizations: "organizations",
  source_url: "source-url",
  x_threads: "x-threads",
};

export function parseFreshAuthEditSection(
  value: string,
): PaperEditSection | null {
  return FRESH_AUTH_EDIT_SECTIONS[value] ?? null;
}

export function usePaperEditState() {
  const [activeEditor, setActiveEditor] = useState<PaperEditSection | null>(null);

  const openEditor = useCallback((section: PaperEditSection) => {
    setActiveEditor(section);
  }, []);

  const setEditorOpen = useCallback(
    (section: PaperEditSection, open: boolean) => {
      setActiveEditor((current) => {
        if (open) return section;
        return current === section ? null : current;
      });
    },
    [],
  );

  return { activeEditor, openEditor, setEditorOpen };
}
