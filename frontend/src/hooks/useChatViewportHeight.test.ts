import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useChatViewportHeight } from "./useChatViewportHeight";

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

it("fills the visible viewport as browser chrome, keyboard, and header sizes change", () => {
  const viewport = Object.assign(new EventTarget(), { height: 740 });
  vi.stubGlobal("visualViewport", viewport);
  const header = document.createElement("header");
  header.className = "app-header";
  let headerHeight = 60;
  Object.defineProperty(header, "offsetHeight", { get: () => headerHeight });
  document.body.append(header);
  let resizeHeader: () => void;
  const disconnect = vi.fn();
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: () => void) { resizeHeader = callback; }
    observe() {}
    disconnect = disconnect;
  });
  const { result, unmount } = renderHook(() => useChatViewportHeight(true));
  expect(result.current).toBe("680px");
  for (const height of [840, 400, 840]) {
    act(() => {
      viewport.height = height;
      viewport.dispatchEvent(new Event("resize"));
    });
    expect(result.current).toBe(`${height - 60}px`);
  }
  act(() => { headerHeight = 90; resizeHeader(); });
  expect(result.current).toBe("750px");
  const remove = vi.spyOn(viewport, "removeEventListener");
  unmount();
  expect(disconnect).toHaveBeenCalledOnce();
  expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
});

it("uses innerHeight when VisualViewport is unavailable", () => {
  vi.stubGlobal("visualViewport", undefined);
  vi.stubGlobal("innerHeight", 800);
  const { result } = renderHook(() => useChatViewportHeight(true));
  expect(result.current).toBe("800px");
  act(() => {
    vi.stubGlobal("innerHeight", 500);
    window.dispatchEvent(new Event("resize"));
  });
  expect(result.current).toBe("500px");
});

it("leaves embedded paper chat sized by its parent", () => {
  const { result } = renderHook(() => useChatViewportHeight(false));
  expect(result.current).toBe("100%");
});
