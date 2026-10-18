import { createContext, useContext } from "react";

import type { PaperLayout } from "@/lib/api/papers";

export interface PdfCitationTarget {
  /** The open paper's layout; undefined while loading, null when it has none. */
  layout: PaperLayout | null | undefined;
  /** Scroll the PDF to a cited block and highlight it. */
  open: (anchor: string) => void;
}

/** Present only in the paper reader, where `pdf:` citations can jump into the PDF. */
export const PdfCitationContext = createContext<PdfCitationTarget | null>(null);

export const usePdfCitationTarget = () => useContext(PdfCitationContext);
