import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import { PdfCitationContext } from "@/components/chat/PdfCitationContext";
import { capitalizeCitationLabel, citationBoxes, citedAnchors, previewPlacement } from "@/components/pdf/pdfCitations";
import type { PaperLayout } from "@/lib/api/papers";

const layout: PaperLayout = {
  page_count: 8,
  processed_pages: 8,
  blocks: {
    p5b1: { page: 5, label: "Section-Header", bbox: [100, 100, 500, 120], section: "p5b1", text: "5.1 Prediction Model" },
    p5b2: { page: 5, label: "Text", bbox: [100, 130, 900, 300], section: "p5b1", text: "MAR consists of an MAE encoder." },
    p6b1: { page: 6, label: "Text", bbox: [100, 50, 900, 200], section: "p5b1", text: "The diffusion MLP denoises." },
    p6b2: { page: 6, label: "Section-Header", bbox: [100, 220, 500, 240], section: "p6b2", text: "5.2 Representation" },
  },
};

const answer = "MAR uses an encoder [Prediction Model](pdf:p5b2) and a head [§5.1](pdf:p5b1), not [made up](pdf:p9b9).";

describe("pdf citation helpers", () => {
  it("covers a block, or a whole section for a header", () => {
    expect(citationBoxes(layout, "p5b2")).toEqual([{ page: 5, bbox: [100, 130, 900, 300] }]);
    expect(citationBoxes(layout, "p5b1").map((box) => box.page)).toEqual([5, 5, 6]);
    expect(citationBoxes(layout, "p9b9")).toEqual([]);
  });

  it("lists cited anchors once, in order", () => {
    expect(citedAnchors(`${answer} Again [x](pdf:p5b2).`)).toEqual(["p5b2", "p5b1", "p9b9"]);
  });
});

describe("ChatMarkdown pdf citations", () => {
  it("renders known anchors as chips that open the passage and lists sources", () => {
    const open = vi.fn();
    render(
      <PdfCitationContext.Provider value={{ layout, open }}>
        <ChatMarkdown text={answer} papers={{}} />
      </PdfCitationContext.Provider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Jump to passage on page 5" }));
    expect(open).toHaveBeenCalledWith("p5b2");
    expect(screen.getByRole("button", { name: "Jump to section on page 5" })).toBeTruthy();
    expect(screen.getByText("made up").closest(".chat-invalid-citation")).not.toBeNull();
    expect(screen.getByText("Sources (2)")).toBeTruthy();
  });

  it("keeps plain labels outside the reader and while streaming", () => {
    const { container, rerender } = render(<ChatMarkdown text={answer} papers={{}} />);
    expect(container.querySelector(".chat-pdf-citation")).toBeNull();
    expect(container.querySelector(".chat-pdf-sources")).toBeNull();

    rerender(
      <PdfCitationContext.Provider value={{ layout, open: vi.fn() }}>
        <ChatMarkdown text={answer} papers={{}} streaming />
      </PdfCitationContext.Provider>,
    );
    expect(container.querySelectorAll(".chat-pdf-citation")).toHaveLength(2);
    expect(container.querySelector(".chat-pdf-sources")).toBeNull();
  });
});

describe("pdf citation preview placement", () => {
  it("opens rightward when there is room and stays inside the viewport near the right edge", () => {
    const viewport = 1200;
    expect(previewPlacement({ left: 100, top: 400 }, viewport)).toEqual({ left: 0, below: false });
    const nearRight = previewPlacement({ left: 1100, top: 400 }, viewport);
    expect(1100 + nearRight.left + 320).toBeLessThanOrEqual(viewport - 12);
  });

  it("stays inside a narrow viewport and opens below chips near the top", () => {
    const placement = previewPlacement({ left: 300, top: 40 }, 390);
    const width = 390 * 0.7;
    expect(300 + placement.left).toBeGreaterThanOrEqual(12);
    expect(300 + placement.left + width).toBeLessThanOrEqual(390 - 12);
    expect(placement.below).toBe(true);
  });
});

describe("citation labels", () => {
  it("sentence-cases labels but keeps deliberate lowercase terms", () => {
    expect(capitalizeCitationLabel("working memory")).toBe("Working memory");
    expect(capitalizeCitationLabel("Hybrid generation")).toBe("Hybrid generation");
    expect(capitalizeCitationLabel("pLDDT scores")).toBe("pLDDT scores");
    expect(capitalizeCitationLabel("§5.1")).toBe("§5.1");
    expect(capitalizeCitationLabel("")).toBe("");
  });

  it("capitalizes the rendered chip label", () => {
    render(
      <PdfCitationContext.Provider value={{ layout, open: vi.fn() }}>
        <ChatMarkdown text="See [working memory](pdf:p5b2)." papers={{}} />
      </PdfCitationContext.Provider>,
    );
    expect(screen.getByRole("button", { name: "Jump to passage on page 5" }).textContent).toContain("Working memory");
  });
});
