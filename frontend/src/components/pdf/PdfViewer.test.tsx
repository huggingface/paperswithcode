import React from "react";
import { act, fireEvent, render as renderWithoutQueries, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

let observedWidth = 800;
let resizeCallback: ResizeObserverCallback | undefined;
let intersecting = true;
const intersectionObservers: Array<{ element: Element; rootMargin: string; callback: IntersectionObserverCallback }> = [];
const reactPdf = vi.hoisted(() => ({
  documentOptions: [] as unknown[],
  renders: [] as Array<() => void>,
  holdRenders: false,
  pageText: [] as string[],
}));
const pageRef = (page: number) => ({ num: page * 10, gen: 0 });
const outlinePdf = (numPages: number, outline: unknown[] = []) => ({
  numPages,
  getOutline: async () => outline,
  getDestination: async () => null,
  getPageIndex: async (ref: { num: number }) => ref.num / 10 - 1,
  getPage: async () => ({ view: [0, 0, 612, 792] }),
});
const unsizedPdf = { ...outlinePdf(13), getPage: async () => { throw new Error("broken page"); } };
const sampleOutline = [
  { title: "Introduction", dest: [pageRef(1), { name: "XYZ" }, 72, 720, null], items: [] },
  { title: "System Design", dest: [pageRef(5), { name: "XYZ" }, 72, 396, null], items: [
    { title: "SSD Streaming Expert Layers", dest: [pageRef(6), { name: "Fit" }], items: [] },
  ] },
  { title: "Evaluation", dest: [pageRef(9), { name: "Fit" }], items: [] },
];

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
    Document: ({ children, onLoadSuccess, onLoadError, onItemClick, options }: {
      children: React.ReactNode;
      onLoadSuccess: (pdf: { numPages: number }) => void;
      onLoadError: (error: Error) => void;
      onItemClick?: (item: { pageNumber: number; pageIndex: number }) => void;
      options?: unknown;
    }) => {
      // Match React-PDF's LinkService, which retains the first callback.
      const initialItemClick = React.useRef(onItemClick);
      reactPdf.documentOptions.push(options);
      return <div>
        <button onClick={() => onLoadSuccess(outlinePdf(1))}>Load PDF</button>
        <button onClick={() => onLoadSuccess(outlinePdf(13))}>Load long PDF</button>
        <button onClick={() => onLoadSuccess(outlinePdf(13, sampleOutline))}>Load outlined PDF</button>
        <button onClick={() => onLoadSuccess(unsizedPdf)}>Load unsized PDF</button>
        <button onClick={() => initialItemClick.current?.({ pageNumber: 13, pageIndex: 12 })}>Citation link</button>
        <button onClick={() => onLoadError(new Error("network response was 404"))}>Fail PDF</button>
        {children}
      </div>;
    },
    Page: ({ width, onRenderSuccess, onRenderTextLayerSuccess }: {
      width: number;
      onRenderSuccess?: () => void;
      onRenderTextLayerSuccess?: () => void;
    }) => {
      React.useEffect(() => {
        if (!onRenderSuccess) return;
        if (reactPdf.holdRenders) reactPdf.renders.push(onRenderSuccess);
        else onRenderSuccess();
      }, [onRenderSuccess]);
      React.useEffect(() => onRenderTextLayerSuccess?.(), [onRenderTextLayerSuccess]);
      return <div data-testid="pdf-page" data-width={width}>
        <div className="textLayer">{reactPdf.pageText.map((text, index) => <span key={index} role="presentation">{text}</span>)}</div>
      </div>;
    },
}));

import { PdfViewer } from "./PdfViewer";
import { highlightPdfText } from "./usePdfSearch";

const render = (ui: React.ReactElement) => renderWithoutQueries(ui, {
  wrapper: ({ children }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>,
});

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
    intersecting = true;
    intersectionObservers.length = 0;
    resizeCallback = undefined;
    reactPdf.documentOptions.length = 0;
    reactPdf.renders.length = 0;
    reactPdf.holdRenders = false;
    reactPdf.pageText = [];
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => observedWidth,
    });
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      value: class {
        constructor(private readonly callback: IntersectionObserverCallback, private readonly options?: IntersectionObserverInit) {}
        observe(element: Element) {
          intersectionObservers.push({ element, rootMargin: this.options?.rootMargin ?? "", callback: this.callback });
          this.callback([{ isIntersecting: intersecting, target: element } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
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

  it("navigates to unmounted pages and persists the visible page after scrolling settles", async () => {
    intersecting = false;
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const onPageChange = vi.fn();
    const props = {
      url: "https://arxiv.org/pdf/2511.09554",
      paperKey: "2511.09554",
      paperTitle: "RF-DETR",
      paperHref: "/paper/2511.09554",
      onPageChange,
    };
    const view = render(<PdfViewer {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    const destination = view.container.querySelector('[data-page="13"]');
    expect(destination).toBeInTheDocument();
    expect(destination?.querySelector('[data-testid="pdf-page"]')).toBeNull();

    const updatedPageChange = vi.fn();
    view.rerender(<PdfViewer {...props} onPageChange={updatedPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Citation link" }));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "smooth" });
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(destination);
    expect(updatedPageChange).not.toHaveBeenCalled();
    view.container.querySelectorAll<HTMLElement>("[data-page]").forEach((element) => {
      vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
        top: element === destination ? 0 : -1000,
        bottom: element === destination ? 900 : -100,
      } as DOMRect);
    });
    fireEvent.scroll(screen.getByRole("region", { name: "Paper PDF" }));
    expect(updatedPageChange).not.toHaveBeenCalled();
    await waitFor(() => expect(updatedPageChange).toHaveBeenCalledWith(13));
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("renders pages ahead of the viewport and keeps them until they are far away", () => {
    intersecting = false;
    const view = render(<PdfViewer url="https://arxiv.org/pdf/2511.09554" paperKey="2511.09554" paperTitle="RF-DETR" paperHref="/paper/2511.09554" />);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    const pageElement = view.container.querySelector('[data-page="8"]')!;
    const fire = (rootMargin: string, isIntersecting: boolean) => act(() => {
      for (const observer of intersectionObservers) {
        if (observer.element !== pageElement || observer.rootMargin !== rootMargin) continue;
        observer.callback([{ isIntersecting, target: pageElement } as IntersectionObserverEntry], {} as IntersectionObserver);
      }
    });
    const rendered = () => pageElement.querySelector('[data-testid="pdf-page"]');
    expect(rendered()).toBeNull();

    fire("250% 0px", true);
    fire("600% 0px", true);
    expect(rendered()).toBeInTheDocument();
    fire("250% 0px", false);
    expect(rendered()).toBeInTheDocument();
    fire("600% 0px", false);
    expect(rendered()).toBeNull();
  });

  it("advances repeated Next clicks while a smooth scroll is still running", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const onPageChange = vi.fn();
    const view = render(<PdfViewer url="/sample.pdf" paperKey="test" paperTitle="Test" paperHref="/" chrome="canvas" onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(view.container.querySelector('[data-page="3"]'));
    expect(screen.getByText("Page 3 of 13")).toBeInTheDocument();
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("re-renders sharp pages at the new width once divider dragging ends", async () => {
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
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "610"));
    expect(screen.getByTestId("pdf-page").closest(".pdf-pages")).toHaveStyle({ "--pdf-live-scale": "1" });
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

  it("keeps the previous render on screen until the zoomed page has painted", async () => {
    render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Load PDF" }));
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790"));
    reactPdf.holdRenders = true;

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));

    const [shown, pending] = screen.getAllByTestId("pdf-page");
    expect(shown).toHaveAttribute("data-width", "790");
    expect(shown.parentElement).toHaveStyle({ "--pdf-layer-scale": String(869 / 790) });
    expect(pending).toHaveAttribute("data-width", "869");
    expect(pending.parentElement).toHaveClass("is-pending");

    act(() => reactPdf.renders.forEach((renderSuccess) => renderSuccess()));
    expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "869");
    expect(screen.getByTestId("pdf-page").parentElement).not.toHaveClass("is-pending");
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

  it("shows a hover table of contents built from the PDF outline and jumps to sections", async () => {
    const scrollTo = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: scrollTo });
    window.history.replaceState(null, "", "/paper/2609.18063/read");
    const onPageChange = vi.fn();
    const onPageChangeSpy = () => onPageChange.mock.lastCall?.[0];
    const view = render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    expect(screen.queryByRole("navigation", { name: "Paper sections" })).not.toBeInTheDocument();

    // Pages are 1000px tall, stacked below a scroller whose top edge is at 100px.
    const scroller = screen.getByRole("region", { name: "Paper PDF" });
    vi.spyOn(scroller, "getBoundingClientRect").mockReturnValue({ top: 100 } as DOMRect);
    const layoutPages = (scrollTop: number) => view.container.querySelectorAll<HTMLElement>("[data-page]").forEach((element) => {
      const top = 100 + (Number(element.dataset.page) - 1) * 1000 - scrollTop;
      vi.spyOn(element, "getBoundingClientRect").mockReturnValue({ top, bottom: top + 1000, height: 1000 } as DOMRect);
    });
    layoutPages(0);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));
    const toc = await screen.findByRole("navigation", { name: "Paper sections" });
    expect(toc.querySelectorAll(".pdf-outline-tick")).toHaveLength(4);
    const links = screen.getAllByRole("link", { name: /Introduction|System Design|SSD Streaming|Evaluation/ });
    expect(links.map((link) => link.textContent)).toEqual(["Introduction", "System Design", "SSD Streaming Expert Layers", "Evaluation"]);
    expect(links[2].closest("li")).toHaveClass("level-1");
    // The Introduction heading starts 9% down page 1, below the reading anchor at the top.
    fireEvent.scroll(scroller);
    await waitFor(() => expect(toc.querySelector(".pdf-outline-tick.is-active")).toBeNull());

    fireEvent.click(screen.getByRole("link", { name: "System Design" }));

    expect(scrollTo).toHaveBeenCalledWith({ top: 4000 + 500 - 8, behavior: "smooth" });
    expect(window.location.hash).toBe("#pdf-section-1");
    expect(screen.getByRole("link", { name: "System Design" })).not.toHaveFocus();
    expect(screen.getByRole("link", { name: "System Design" })).toHaveAttribute("aria-current", "location");
    expect(toc.querySelector(".pdf-outline-tick.is-active")).toBe(toc.querySelectorAll(".pdf-outline-tick")[1]);

    // Once the smooth scroll lands, the section under the anchor stays active
    // even though the viewport centre is already on the next page.
    layoutPages(4000 + 500 - 8);
    fireEvent.scroll(scroller);
    await waitFor(() => expect(onPageChangeSpy()).toBe(5));
    expect(screen.getByRole("link", { name: "System Design" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "SSD Streaming Expert Layers" })).not.toHaveAttribute("aria-current");
  });

  it("opens author pages from the paper's own authors' names on the first page", async () => {
    reactPdf.pageText = ["Longformer", "Iz Beltagy", "∗ ", "Matthew E. Peters", "{beltagy}@allenai.org"];
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 500, 1000));
    Object.defineProperty(Range.prototype, "getClientRects", {
      configurable: true,
      value: () => [new DOMRect(100, 50, 80, 10)],
    });
    const authors = [{ id: "6438", name: "Iz Beltagy" }, { id: "9515", name: "Matthew E. Peters" }, { id: "1", name: "Someone Else" }];
    const view = renderWithoutQueries(<QueryClientProvider client={new QueryClient()}><MemoryRouter>
      <PdfViewer url="https://arxiv.org/pdf/2004.05150" paperKey="2004.05150" paperTitle="Longformer" paperHref="/paper/2004.05150" authors={authors} />
    </MemoryRouter></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    const beltagy = await screen.findByRole("link", { name: "Author Iz Beltagy" });
    expect(beltagy).toHaveAttribute("href", "/authors/6438");
    expect(beltagy.parentElement).toHaveStyle({ left: "20%", top: "5%", width: "16%", height: "1%" });
    expect(screen.getByRole("link", { name: "Author Matthew E. Peters" })).toHaveAttribute("href", "/authors/9515");
    expect(screen.getAllByRole("link", { name: /^Author / })).toHaveLength(2);
    expect(view.container.querySelectorAll('[data-page="2"] .pdf-author-link')).toHaveLength(0);
    vi.restoreAllMocks();
  });

  it("sizes unrendered page placeholders from the document's page proportions", async () => {
    intersecting = false;
    const view = render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" />);
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    const placeholder = view.container.querySelector<HTMLElement>('[data-page="13"]');
    expect(placeholder).toHaveStyle({ minHeight: `${Math.round(790 * 1.35)}px` });
    await waitFor(() => expect(placeholder).toHaveStyle({ minHeight: `${Math.round(790 * 792 / 612)}px` }));
  });

  it("still restores the remembered page when the first page cannot be sized", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const onPageChange = vi.fn();
    const view = render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" initialPage={7} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Load unsized PDF" }));

    await waitFor(() => expect(onPageChange).toHaveBeenCalledWith(7));
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(view.container.querySelector('[data-page="7"]'));
    expect(view.container.querySelector<HTMLElement>('[data-page="13"]')).toHaveStyle({ minHeight: `${Math.round(790 * 1.35)}px` });
  });

  it("toggles the table of contents open on tap and closes it with Escape without leaving the reader", async () => {
    const onClose = vi.fn();
    render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));
    const rail = await screen.findByRole("button", { name: "Table of contents" });
    expect(rail).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(rail);
    expect(rail).toHaveAttribute("aria-expanded", "true");
    expect(rail.closest(".pdf-outline")).toHaveClass("is-pinned");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(rail).toHaveAttribute("aria-expanded", "false");
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("swells ticks under a dragged finger and jumps to the section where it lifts", async () => {
    const scrollTo = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: scrollTo });
    window.history.replaceState(null, "", "/paper/2609.18063/read");
    render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" />);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));
    const rail = await screen.findByRole("button", { name: "Table of contents" });
    const ticks = [...rail.querySelectorAll<HTMLElement>(".pdf-outline-tick")];
    ticks.forEach((tick, position) => vi.spyOn(tick, "getBoundingClientRect").mockReturnValue({ top: position * 10, height: 2 } as DOMRect));

    rail.focus();
    fireEvent.pointerDown(rail, { pointerType: "touch", pointerId: 1, clientY: 0 });
    expect(ticks[0]).toHaveClass("is-scrubbed");
    expect(document.querySelector(".pdf-outline-scrub-label")).toBeNull();
    fireEvent.pointerMove(rail, { pointerType: "touch", pointerId: 1, clientY: 25 });
    expect(ticks[2]).toHaveClass("is-scrubbed");
    expect(ticks[2].style.getPropertyValue("--pop")).toBe("1");
    expect(Number(ticks[1].style.getPropertyValue("--pop"))).toBeCloseTo(2 / 3);
    expect(document.querySelector(".pdf-outline-scrub-label")).toHaveTextContent("SSD Streaming Expert Layers");

    fireEvent.pointerUp(rail, { pointerType: "touch", pointerId: 1, clientY: 25 });
    fireEvent.click(rail);
    expect(window.location.hash).toBe("#pdf-section-2");
    expect(scrollTo).toHaveBeenCalled();
    expect(rail).toHaveAttribute("aria-expanded", "false");
    expect(rail).not.toHaveFocus();
    expect(document.querySelector(".pdf-outline-scrub-label")).toBeNull();
    expect(ticks[2]).not.toHaveClass("is-scrubbed");

    // A plain tap still toggles the list open.
    fireEvent.pointerDown(rail, { pointerType: "touch", pointerId: 2, clientY: 0 });
    fireEvent.pointerUp(rail, { pointerType: "touch", pointerId: 2, clientY: 0 });
    fireEvent.click(rail);
    expect(rail).toHaveAttribute("aria-expanded", "true");
  });

  it("highlights the section list entry for the tick under the mouse", async () => {
    render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" />);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));
    const rail = await screen.findByRole("button", { name: "Table of contents" });
    rail.querySelectorAll<HTMLElement>(".pdf-outline-tick").forEach((tick, position) => {
      vi.spyOn(tick, "getBoundingClientRect").mockReturnValue({ top: position * 10, height: 2 } as DOMRect);
    });
    const panel = rail.closest("nav")!.querySelector<HTMLElement>(".pdf-outline-panel")!;
    Object.defineProperty(panel, "clientHeight", { configurable: true, value: 30 });
    panel.querySelectorAll("li").forEach((entry, position) => {
      Object.defineProperty(entry, "offsetTop", { configurable: true, value: position * 20 });
      Object.defineProperty(entry, "offsetHeight", { configurable: true, value: 20 });
    });

    fireEvent.pointerMove(rail, { pointerType: "mouse", clientY: 31 });
    expect(screen.getByRole("link", { name: "Evaluation" })).toHaveClass("is-scrubbed");
    expect(screen.getByRole("link", { name: "System Design" })).not.toHaveClass("is-scrubbed");
    // The panel centres the entry (60–80px) in its 30px view.
    expect(panel.scrollTop).toBe(55);
    expect(document.querySelector(".pdf-outline-scrub-label")).toBeNull();

    fireEvent.pointerLeave(rail, { pointerType: "mouse" });
    expect(panel.querySelector(".is-scrubbed")).toBeNull();
  });

  it("opens a #pdf-section deep link instead of the remembered page", async () => {
    const placeholderHeightsAtScroll: string[] = [];
    const scrollTo = vi.fn(function (this: HTMLElement) {
      placeholderHeightsAtScroll.push(this.querySelector<HTMLElement>('[data-page="13"]')?.style.minHeight ?? "");
    });
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: scrollTo });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    window.history.replaceState(null, "", "/paper/2609.18063/read#pdf-section-3");
    const onPageChange = vi.fn();
    render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" initialPage={7} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));

    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "instant" })));
    expect(scrollIntoView).not.toHaveBeenCalled();
    // Placeholders already had the document's real proportions when the jump measured them.
    expect(placeholderHeightsAtScroll).toEqual([`${Math.round(790 * 792 / 612)}px`]);
    // jsdom reports zero-size pages, so the scroll tracker later snaps back to page 1.
    expect(onPageChange).toHaveBeenCalledWith(9);
    window.history.replaceState(null, "", "/paper/2609.18063/read");
  });

  it("falls back to the remembered page when a #pdf-section deep link cannot be resolved", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    window.history.replaceState(null, "", "/paper/2609.18063/read#pdf-section-99");
    const onPageChange = vi.fn();
    const view = render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" initialPage={7} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Load outlined PDF" }));

    await waitFor(() => expect(onPageChange).toHaveBeenCalledWith(7));
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(view.container.querySelector('[data-page="7"]'));

    // The same holds for a document without any bookmarks.
    onPageChange.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    await waitFor(() => expect(onPageChange).toHaveBeenCalledWith(7));
    window.history.replaceState(null, "", "/paper/2609.18063/read");
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

  it("reloads the document from scratch on Retry", () => {
    render(<PdfViewer url="https://arxiv.org/pdf/2609.18063" paperKey="2609.18063" paperTitle="edge0" paperHref="/paper/2609.18063" />);
    fireEvent.click(screen.getByRole("button", { name: "Fail PDF" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF source could not be loaded in this browser.");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load long PDF" }));
    expect(screen.getByRole("region", { name: "Paper PDF" }).querySelectorAll("[data-page]")).toHaveLength(13);
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
    expect(reactPdf.documentOptions).not.toHaveLength(0);
    expect(reactPdf.documentOptions.every((options) => options === reactPdf.documentOptions[0])).toBe(true);
    expect(reactPdf.documentOptions[0]).toEqual({ disableStream: true, disableAutoFetch: true });

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
