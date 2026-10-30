import { useEffect } from "react";

import { DEFAULT_SITE_SUFFIX } from "@/lib/latexPlainText";

/** Shows `title` while mounted, then the site title (or, with `restorePrevious`, the title it replaced). */
export function useDocumentTitle(title: string | undefined, { restorePrevious = false } = {}) {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = restorePrevious ? previous : DEFAULT_SITE_SUFFIX;
    };
  }, [title, restorePrevious]);
}
