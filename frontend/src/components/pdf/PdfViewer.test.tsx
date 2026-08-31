import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let observedWidth = 800;
let resizeCallback: ResizeObserverCallback | undefined;
const reactPdf = vi.hoisted(() => ({ documentOptions: [] as unknown[] }));

vi.mock("@/lib/pdf", () => ({
  assertPdfWorkerConfigured: vi.fn(),
}));

vi.mock("./PdfToolbar", () => ({
  PdfToolbar: ({ searchOpen, onZoomIn, onToggleSearch, onCloseSearch }: {
    searchOpen: boolean;
    onZoomIn: () => void;
    onToggleSearch: () => void;
    onCloseSearch: () => void;
  }) => <div>
    PDF toolbar
    <button type="button" onClick={onZoomIn}>Zoom in</button>
    <button type="button" onClick={onToggleSearch}>Search</button>
    {searchOpen && <button type="button" onClick={onCloseSearch}>Close search</button>}
  </div>,
}));

vi.mock("react-pdf", () => ({
    Document: ({ children, onLoadSuccess, onLoadError, options }: {
      children: React.ReactNode;
      onLoadSuccess: (pdf: { numPages: number }) => void;
      onLoadError: (error: Error) => void;
      options?: unknown;
    }) => {
      reactPdf.documentOptions.push(options);
      return <div>
        <button onClick={() => onLoadSuccess({ numPages: 1 })}>Load PDF</button>
        <button onClick={() => onLoadError(new Error("network response was 404"))}>Fail PDF</button>
        {children}
      </div>;
    },
    Page: ({ width }: { width: number }) => <div data-testid="pdf-page" data-width={width} />,
}));

import { highlightPdfText, PdfViewer } from "./PdfViewer";

describe("highlightPdfText", () => {
  it("escapes PDF text and wraps every case-insensitive match", () => {
    expect(highlightPdfText("Alpha & <ALPHA>", "alpha", true)).toBe(
      '<mark class="pdf-search-highlight is-active">Alpha</mark> &amp; &lt;'
      + '<mark class="pdf-search-highlight is-active">ALPHA</mark>&gt;',
    );
  });

  it("returns safely escaped text when there is no match", () => {
    expect(highlightPdfText('<script>alert("x")</script>', "missing", false)).toBe(
      "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
    );
  });
});

describe("PdfViewer resize rendering", () => {
  beforeEach(() => {
    observedWidth = 800;
    resizeCallback = undefined;
    reactPdf.documentOptions.length = 0;
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => observedWidth,
    });
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      value: class {
        constructor(private readonly callback: IntersectionObserverCallback) {}
        observe(element: Element) {
          this.callback([{ isIntersecting: true, target: element } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
        }
        disconnect() {}
        unobserve() {}
        takeRecords() { return []; }
        root = null;
        rootMargin = "";
        thresholds = [];
      },
    });
    Object.defineProperty(window, "ResizeObserver", {
      configurable: true,
      value: class {
        constructor(callback: ResizeObserverCallback) { resizeCallback = callback; }
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    });
  });

  it("keeps the rendered pages and live scale after divider dragging ends", async () => {
    const view = render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Load PDF" }));
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790"));

    view.rerender(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
      resizeActive
    />);
    observedWidth = 620;
    act(() => resizeCallback?.([], {} as ResizeObserver));
    expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790");
    expect(screen.getByTestId("pdf-page").closest(".pdf-pages")).toHaveStyle({
      "--pdf-live-scale": String(610 / 790),
    });

    view.rerender(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790"));
    expect(screen.getByTestId("pdf-page").closest(".pdf-pages")).toHaveStyle({
      "--pdf-live-scale": String(610 / 790),
    });
  });

  it("centers the document horizontally after zooming", () => {
    render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    const scrollSurface = screen.getByRole("region", { name: "Paper PDF" });
    Object.defineProperty(scrollSurface, "scrollWidth", { configurable: true, value: 1200 });

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));

    expect(scrollSurface.scrollLeft).toBe(200);
  });

  it("zooms on a trackpad pinch without blocking ordinary scrolling", async () => {
    render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Load PDF" }));
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790"));
    const scrollSurface = screen.getByRole("region", { name: "Paper PDF" });
    const scrollEvent = new WheelEvent("wheel", { cancelable: true, deltaY: 40 });
    scrollSurface.dispatchEvent(scrollEvent);
    expect(scrollEvent.defaultPrevented).toBe(false);

    const pinchEvent = new WheelEvent("wheel", { cancelable: true, ctrlKey: true, deltaY: -100 });
    scrollSurface.dispatchEvent(pinchEvent);

    expect(pinchEvent.defaultPrevented).toBe(true);
    await waitFor(() => expect(Number(
      screen.getByTestId("pdf-page").closest<HTMLElement>(".pdf-pages")?.style
        .getPropertyValue("--pdf-live-scale"),
    )).toBeGreaterThan(1));
    expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790");
    await waitFor(() => expect(Number(screen.getByTestId("pdf-page").dataset.width)).toBeGreaterThan(790));
  });

  it("closes PDF search with Escape", () => {
    render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByRole("button", { name: "Close search" })).toBeVisible();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Close search" })).not.toBeInTheDocument();
  });

  it("shows a preparation message for an archived PDF that is not ready yet", () => {
    const props = {
      url: "/paper-assets/external/109743/paper.pdf",
      paperKey: "109743",
      paperTitle: "External report",
      paperHref: "/paper/109743",
      loadErrorMessage: "Paper content is still being prepared. Please try again later.",
    } as React.ComponentProps<typeof PdfViewer> & { loadErrorMessage: string };
    render(<PdfViewer {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Fail PDF" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Paper content is still being prepared. Please try again later.",
    );
  });

  it("provides application-owned canvas controls for a private paper preview", async () => {
    render(<PdfViewer
      url="/api/v1/chat/artifacts/paper-1/versions/version-1/preview"
      paperKey="paper-1:version-1"
      paperTitle="Careful Draft"
      paperHref="/chat"
      chrome="canvas"
    />);

    fireEvent.click(screen.getByRole("button", { name: "Load PDF" }));

    expect(screen.getByRole("region", { name: "Careful Draft PDF preview" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Fit to width" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href", "/api/v1/chat/artifacts/paper-1/versions/version-1/preview",
    );
    expect(screen.getByText("Page 1 of 1")).toBeVisible();
  });

  it("keeps PDF credentials scoped to private canvas previews", () => {
    const reader = render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(reactPdf.documentOptions.every((options) => options === undefined)).toBe(true);

    reader.unmount();
    reactPdf.documentOptions.length = 0;
    render(<PdfViewer
      url="/api/v1/chat/artifacts/paper-1/versions/version-1/preview"
      paperKey="paper-1:version-1"
      paperTitle="Careful Draft"
      paperHref="/chat"
      chrome="canvas"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(reactPdf.documentOptions).not.toHaveLength(0);
    expect(reactPdf.documentOptions.every((options) => options === reactPdf.documentOptions[0])).toBe(true);
    expect(reactPdf.documentOptions[0]).toEqual({ withCredentials: true });
  });
});
