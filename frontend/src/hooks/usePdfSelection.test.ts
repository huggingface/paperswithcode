import { afterEach, describe, expect, it, vi } from "vitest";

import type { PaperSelectionDraft } from "@/lib/chat";
import {
  PDF_SELECTION_ERRORS,
  commitPdfSelection,
  normalizePaperSelectionText,
  paperSelectionFingerprint,
  paperSelectionUtf8Bytes,
  parseChatDraft,
  parsePaperSelectionDraft,
} from "@/lib/paperSelection";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { act, renderHook } from "@testing-library/react";
import { useRef } from "react";

function textNode(text: string): Text {
  return document.createTextNode(text);
}

function pageLayer(page: number, text: string) {
  const pageEl = document.createElement("div");
  pageEl.className = "pdf-page";
  pageEl.dataset.page = String(page);
  const layer = document.createElement("div");
  layer.className = "textLayer";
  const span = document.createElement("span");
  span.append(textNode(text));
  layer.append(span);
  pageEl.append(layer);
  return { pageEl, layer, span };
}

function mockSelection(range: Range, extra?: Partial<Selection>): Selection {
  return {
    rangeCount: 1,
    isCollapsed: range.collapsed,
    getRangeAt: () => range,
    toString: () => range.toString(),
    anchorNode: range.startContainer,
    focusNode: range.endContainer,
    ...extra,
  } as Selection;
}

function primaryPointer(type: "pointerdown" | "pointerup" | "pointercancel") {
  const event = new PointerEvent(type, {
    bubbles: true,
    button: 0,
    pointerType: "mouse",
  });
  Object.defineProperty(event, "isPrimary", { value: true });
  return event;
}

async function flushSelectionCommit() {
  await act(async () => {
    vi.advanceTimersByTime(20);
    await Promise.resolve();
  });
}

describe("paper selection normalization", () => {
  it("converts CRLF and NBSP, preserves newlines, and collapses layout spaces", () => {
    expect(normalizePaperSelectionText("A\r\nB\u00a0\u00a0C   D")).toBe("A\nB C D");
    expect(normalizePaperSelectionText("  keep\n  lines  ")).toBe("keep\n lines");
  });

  it("rejects malformed stored attachments without dropping visible text", () => {
    expect(parsePaperSelectionDraft({
      routeId: "2608.09119",
      paperVersion: "v1",
      page: 4,
      text: "quoted evidence",
    })).toEqual({
      routeId: "2608.09119",
      paperVersion: "v1",
      page: 4,
      text: "quoted evidence",
    });
    expect(parsePaperSelectionDraft({ routeId: "x", paperVersion: "v1", page: 1, text: "   " })).toBeUndefined();
    expect(parseChatDraft({
      text: "Ask about this",
      paperMentions: [],
      paperSelection: { routeId: "x" },
    })).toEqual({ text: "Ask about this", paperMentions: [] });
    expect(parseChatDraft("legacy prompt")).toEqual({ text: "legacy prompt", paperMentions: [] });
  });
});

describe("commitPdfSelection", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("captures a range in a web paper's Markdown as its single page", () => {
    const root = document.createElement("div");
    const article = document.createElement("article");
    article.className = "reader-web-document";
    article.dataset.page = "1";
    const paragraph = document.createElement("p");
    paragraph.append(textNode("It scores 48.09 on LiveClaw."));
    article.append(paragraph);
    root.append(article);
    document.body.append(root);
    const range = document.createRange();
    range.setStart(paragraph.firstChild as Text, 10);
    range.setEnd(paragraph.firstChild as Text, 27);

    expect(commitPdfSelection({
      selection: mockSelection(range),
      pagesRoot: root,
      routeId: "123294",
      paperVersion: "v1",
      numPages: 1,
    })).toEqual({
      ok: true,
      selection: { routeId: "123294", paperVersion: "v1", page: 1, text: "48.09 on LiveClaw" },
    });
  });

  it("captures one in-page text-layer range, including search mark text", () => {
    const root = document.createElement("div");
    root.className = "pdf-pages";
    const first = pageLayer(4, "plain ");
    const mark = document.createElement("mark");
    mark.textContent = "α = 1";
    first.layer.append(mark);
    root.append(first.pageEl);
    document.body.append(root);
    const range = document.createRange();
    range.setStart(first.span.firstChild as Text, 0);
    range.setEnd(mark.firstChild as Text, mark.textContent!.length);
    const result = commitPdfSelection({
      selection: mockSelection(range),
      pagesRoot: root,
      routeId: "2608.09119",
      paperVersion: "v1",
      numPages: 12,
    });
    expect(result).toEqual({
      ok: true,
      selection: {
        routeId: "2608.09119",
        paperVersion: "v1",
        page: 4,
        text: "plain α = 1",
      },
    });
    expect(paperSelectionFingerprint((result as { selection: PaperSelectionDraft }).selection))
      .toContain("2608.09119");
  });

  it("ignores collapsed ranges and rejects cross-page, outside, and oversized quotes", () => {
    const root = document.createElement("div");
    root.className = "pdf-pages";
    const first = pageLayer(1, "page one");
    const second = pageLayer(2, "page two");
    root.append(first.pageEl, second.pageEl);
    const outside = document.createElement("p");
    outside.textContent = "chrome";
    document.body.append(root, outside);

    const collapsed = document.createRange();
    collapsed.setStart(first.span.firstChild as Text, 0);
    collapsed.collapse(true);
    expect(commitPdfSelection({
      selection: mockSelection(collapsed),
      pagesRoot: root,
      routeId: "1",
      paperVersion: "v1",
    })).toEqual({ ok: false, error: null });

    const cross = document.createRange();
    cross.setStart(first.span.firstChild as Text, 0);
    cross.setEnd(second.span.firstChild as Text, 4);
    expect(commitPdfSelection({
      selection: mockSelection(cross),
      pagesRoot: root,
      routeId: "1",
      paperVersion: "v1",
    })).toEqual({ ok: false, error: PDF_SELECTION_ERRORS.crossPage });

    const chrome = document.createRange();
    chrome.selectNodeContents(outside);
    expect(commitPdfSelection({
      selection: mockSelection(chrome),
      pagesRoot: root,
      routeId: "1",
      paperVersion: "v1",
    })).toEqual({ ok: false, error: PDF_SELECTION_ERRORS.outside });

    const huge = "é".repeat(8_001);
    first.span.firstChild!.textContent = huge;
    const oversized = document.createRange();
    oversized.selectNodeContents(first.span);
    expect(commitPdfSelection({
      selection: mockSelection(oversized),
      pagesRoot: root,
      routeId: "1",
      paperVersion: "v1",
    })).toEqual({ ok: false, error: PDF_SELECTION_ERRORS.tooLarge });
    expect(paperSelectionUtf8Bytes("é".repeat(6_000))).toBeGreaterThan(8_000);
  });
});

describe("usePdfSelection", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("commits once on pointerup and ignores intermediate selectionchange", async () => {
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    });
    const root = document.createElement("div");
    root.className = "pdf-pages";
    const first = pageLayer(1, "alpha beta");
    root.append(first.pageEl);
    document.body.append(root);
    const onSelect = vi.fn();
    const onError = vi.fn();
    const { unmount } = renderHook(() => {
      const pagesRoot = useRef<HTMLElement | null>(root);
      usePdfSelection({
        enabled: true,
        pagesRoot,
        routeId: "2608.09119",
        paperVersion: "v1",
        numPages: 3,
        onSelect,
        onError,
      });
    });

    const full = document.createRange();
    full.selectNodeContents(first.span);
    const partial = document.createRange();
    partial.setStart(first.span.firstChild as Text, 0);
    partial.setEnd(first.span.firstChild as Text, 5);

    first.span.dispatchEvent(primaryPointer("pointerdown"));
    vi.spyOn(window, "getSelection").mockReturnValue(mockSelection(partial));
    document.dispatchEvent(new Event("selectionchange"));
    act(() => { vi.advanceTimersByTime(400); });
    expect(onSelect).not.toHaveBeenCalled();

    vi.spyOn(window, "getSelection").mockReturnValue(mockSelection(full));
    first.span.dispatchEvent(primaryPointer("pointerup"));
    await act(async () => { await Promise.resolve(); });
    expect(onSelect).not.toHaveBeenCalled();
    await flushSelectionCommit();
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith({
      routeId: "2608.09119",
      paperVersion: "v1",
      page: 1,
      text: "alpha beta",
    });
    expect(onError).not.toHaveBeenCalled();
    unmount();
  });

  it("commits keyboard Shift+navigation and a stable selectionchange fallback once", async () => {
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    });
    const root = document.createElement("div");
    root.className = "pdf-pages";
    const first = pageLayer(1, "alpha beta");
    root.append(first.pageEl);
    document.body.append(root);
    const onSelect = vi.fn();
    const { unmount } = renderHook(() => {
      const pagesRoot = useRef<HTMLElement | null>(root);
      usePdfSelection({
        enabled: true,
        pagesRoot,
        routeId: "2608.09119",
        paperVersion: "v1",
        onSelect,
      });
    });
    const range = document.createRange();
    range.selectNodeContents(first.span);
    vi.spyOn(window, "getSelection").mockReturnValue(mockSelection(range));

    first.span.dispatchEvent(new KeyboardEvent("keyup", {
      bubbles: true, key: "ArrowRight", shiftKey: true,
    }));
    await flushSelectionCommit();
    expect(onSelect).toHaveBeenCalledTimes(1);

    document.dispatchEvent(new Event("selectionchange"));
    act(() => { vi.advanceTimersByTime(400); });
    expect(onSelect).toHaveBeenCalledTimes(1);
    unmount();
    onSelect.mockClear();
    first.span.dispatchEvent(primaryPointer("pointerup"));
    await flushSelectionCommit();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("reattaches the same passage in a later gesture and ignores pointer cancellation", async () => {
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
    });
    const root = document.createElement("div");
    root.className = "pdf-pages";
    const first = pageLayer(1, "alpha beta");
    root.append(first.pageEl);
    document.body.append(root);
    const onSelect = vi.fn();
    const { unmount } = renderHook(() => {
      const pagesRoot = useRef<HTMLElement | null>(root);
      usePdfSelection({
        enabled: true,
        pagesRoot,
        routeId: "2608.09119",
        paperVersion: "v1",
        onSelect,
      });
    });
    const range = document.createRange();
    range.selectNodeContents(first.span);
    vi.spyOn(window, "getSelection").mockReturnValue(mockSelection(range));

    first.span.dispatchEvent(primaryPointer("pointerdown"));
    first.span.dispatchEvent(primaryPointer("pointerup"));
    await flushSelectionCommit();
    expect(onSelect).toHaveBeenCalledTimes(1);

    first.span.dispatchEvent(primaryPointer("pointerdown"));
    first.span.dispatchEvent(primaryPointer("pointerup"));
    await flushSelectionCommit();
    expect(onSelect).toHaveBeenCalledTimes(2);

    first.span.dispatchEvent(primaryPointer("pointerdown"));
    first.span.dispatchEvent(primaryPointer("pointercancel"));
    document.dispatchEvent(new Event("selectionchange"));
    act(() => { vi.advanceTimersByTime(400); });
    await flushSelectionCommit();
    expect(onSelect).toHaveBeenCalledTimes(2);
    unmount();
  });
});
