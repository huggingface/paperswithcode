import { useState, type ReactNode } from "react";
import { FileText } from "lucide-react";

import { citedAnchors, previewPlacement, type PreviewPlacement } from "@/components/pdf/pdfCitations";
import { usePdfCitationTarget } from "./PdfCitationContext";

function preview(text: string): string {
  return text.length > 220 ? `${text.slice(0, 220).trimEnd()}…` : text;
}

/** An inline chip that jumps to the cited passage in the open PDF. */
export function PdfCitationChip({ anchor, children }: { anchor: string; children: ReactNode }) {
  const target = usePdfCitationTarget();
  const [placement, setPlacement] = useState<PreviewPlacement>({ left: 0, below: false });
  const block = target?.layout?.blocks[anchor];
  if (!target || !block) {
    // Outside the reader, before the layout loads, or an anchor the paper does
    // not have: keep the label, never a link that goes nowhere.
    return <span className="chat-invalid-citation">{children}</span>;
  }
  const isSection = block.label === "Section-Header";
  const place = (element: HTMLElement) =>
    setPlacement(previewPlacement(element.getBoundingClientRect(), window.innerWidth));
  return <button
    type="button"
    className="chat-pdf-citation"
    onClick={() => target.open(anchor)}
    onMouseEnter={(event) => place(event.currentTarget)}
    onFocus={(event) => place(event.currentTarget)}
    aria-label={`${isSection ? "Jump to section" : "Jump to passage"} on page ${block.page}`}
  >
    <FileText aria-hidden="true" />
    <span>{children}</span>
    <span
      className={`chat-pdf-citation-preview${placement.below ? " is-below" : ""}`}
      role="tooltip"
      style={{ left: placement.left }}
    >
      <strong>Page {block.page}{isSection ? " · section" : ""}</strong>
      {block.text && <span>{preview(block.text)}</span>}
    </span>
  </button>;
}

/** A collapsed list of an answer's PDF citations with their pages. */
export function PdfCitationSources({ text }: { text: string }) {
  const target = usePdfCitationTarget();
  const layout = target?.layout;
  if (!target || !layout) return null;
  const anchors = citedAnchors(text).filter((anchor) => layout.blocks[anchor]);
  if (!anchors.length) return null;
  return <details className="chat-pdf-sources">
    <summary>Sources ({anchors.length})</summary>
    <ol>
      {anchors.map((anchor) => {
        const block = layout.blocks[anchor];
        return <li key={anchor}>
          <button type="button" onClick={() => target.open(anchor)}>
            <span className="chat-pdf-sources-page">p. {block.page}</span>
            <span>{preview(block.text) || block.label}</span>
          </button>
        </li>;
      })}
    </ol>
  </details>;
}
