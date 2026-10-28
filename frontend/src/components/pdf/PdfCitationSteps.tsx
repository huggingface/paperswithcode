import { ChevronDown, ChevronUp, X } from "lucide-react";

// Floats over the PDF after a bibliography card's jump so readers can step
// through every place the text cites that entry. The reader's Escape handler
// closes it before leaving the reader.
export function PdfCitationSteps({ index, count, onStep, onClose }: {
  index: number;
  count: number;
  onStep: (direction: 1 | -1) => void;
  onClose: () => void;
}) {
  return <div
    className="pdf-citation-steps"
    role="group"
    aria-label="Citations of this reference"
  >
    <span role="status">Citation {index + 1} of {count}</span>
    <button type="button" onClick={() => onStep(-1)} aria-label="Previous citation" title="Previous citation">
      <ChevronUp size={16} aria-hidden="true" />
    </button>
    <button type="button" onClick={() => onStep(1)} aria-label="Next citation" title="Next citation">
      <ChevronDown size={16} aria-hidden="true" />
    </button>
    <button type="button" onClick={onClose} aria-label="Close citations" title="Close citations">
      <X size={16} aria-hidden="true" />
    </button>
  </div>;
}
