import { useCallback, useState } from "react";

import type { PaperEditSection } from "@/lib/paperCuration";

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
