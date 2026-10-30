import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

import { clampZoom } from "./pdfZoom";

interface ZoomAnchor {
  page: HTMLElement;
  fraction: number;
  viewportOffset: number;
}

// Zooming keeps the document point under the anchor (the pointer, or the
// viewport center) in place instead of drifting with the growing pages above it.
function captureZoomAnchor(scroller: HTMLElement, clientY?: number): ZoomAnchor | undefined {
  const top = scroller.getBoundingClientRect().top;
  const anchorY = clientY ?? top + scroller.clientHeight / 2;
  for (const page of scroller.querySelectorAll<HTMLElement>("[data-page]")) {
    const rect = page.getBoundingClientRect();
    if (rect.bottom < anchorY) continue;
    const fraction = rect.height ? Math.max(0, (anchorY - rect.top) / rect.height) : 0;
    return { page, fraction, viewportOffset: anchorY - top };
  }
  return undefined;
}

function restoreZoomAnchor(scroller: HTMLElement, anchor: ZoomAnchor) {
  const rect = anchor.page.getBoundingClientRect();
  const anchorY = scroller.getBoundingClientRect().top + anchor.viewportOffset;
  scroller.scrollTop += rect.top + rect.height * anchor.fraction - anchorY;
}

/**
 * Page width for the scroll surface: fit to its width, times the zoom. Divider
 * drags and trackpad pinches only scale the rendered pages through
 * `--pdf-live-scale` on the pages element until they settle.
 */
export function usePdfZoom(
  scrollRef: RefObject<HTMLDivElement>,
  pagesRef: RefObject<HTMLDivElement>,
  resizeActive: boolean,
) {
  const recenterAfterZoom = useRef(false);
  const zoomAnchor = useRef<ZoomAnchor>();
  const pinchDelta = useRef(0);
  const pinchClientY = useRef<number>();
  const pinchFrame = useRef(0);
  const pinchCommitTimer = useRef(0);
  const renderedZoom = useRef(1);
  const liveZoom = useRef(1);
  const liveResizeScale = useRef(1);
  const [fitWidth, setFitWidth] = useState(700);
  const [zoom, setZoom] = useState(1);
  const pageWidth = Math.max(120, Math.round(fitWidth * zoom));

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const update = () => {
      const nextWidth = Math.max(240, element.clientWidth - 10);
      // While the divider or chat toggle moves, the rendered pages only scale.
      // Once it settles, the new width is committed: each page keeps its last
      // canvas scaled until a sharp one at the new width has painted, and the
      // live scale returns to 1 in the same commit.
      liveResizeScale.current = resizeActive ? nextWidth / fitWidth : 1;
      if (resizeActive) {
        pagesRef.current?.style.setProperty("--pdf-live-scale", String(liveResizeScale.current));
      } else {
        setFitWidth(nextWidth);
      }
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitWidth, pagesRef, resizeActive, scrollRef]);

  useLayoutEffect(() => {
    renderedZoom.current = zoom;
    pagesRef.current?.style.setProperty("--pdf-live-scale", String(liveResizeScale.current));
    const element = scrollRef.current;
    if (element && zoomAnchor.current) restoreZoomAnchor(element, zoomAnchor.current);
    zoomAnchor.current = undefined;
    if (!recenterAfterZoom.current) return;
    if (element) {
      element.scrollLeft = Math.max(0, (element.scrollWidth - element.clientWidth) / 2);
    }
    recenterAfterZoom.current = false;
  }, [pageWidth, pagesRef, resizeActive, scrollRef, zoom]);

  const setCenteredZoom = useCallback((nextZoom: (value: number) => number) => {
    window.clearTimeout(pinchCommitTimer.current);
    const next = clampZoom(nextZoom(liveZoom.current));
    liveZoom.current = next;
    recenterAfterZoom.current = next !== renderedZoom.current;
    if (recenterAfterZoom.current && scrollRef.current) zoomAnchor.current = captureZoomAnchor(scrollRef.current);
    setZoom(next);
  }, [scrollRef]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const handlePinch = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      pinchDelta.current += event.deltaY;
      pinchClientY.current = event.clientY;
      if (pinchFrame.current) return;
      pinchFrame.current = requestAnimationFrame(() => {
        const delta = pinchDelta.current;
        pinchDelta.current = 0;
        pinchFrame.current = 0;
        const next = clampZoom(liveZoom.current * Math.exp(-delta * 0.002));
        liveZoom.current = next;
        const anchor = captureZoomAnchor(element, pinchClientY.current);
        pagesRef.current?.style.setProperty(
          "--pdf-live-scale",
          String(liveResizeScale.current * next / renderedZoom.current),
        );
        if (anchor) restoreZoomAnchor(element, anchor);
        window.clearTimeout(pinchCommitTimer.current);
        pinchCommitTimer.current = window.setTimeout(() => {
          recenterAfterZoom.current = next !== renderedZoom.current;
          if (recenterAfterZoom.current) zoomAnchor.current = captureZoomAnchor(element, pinchClientY.current);
          setZoom(liveZoom.current);
        }, 180);
      });
    };
    element.addEventListener("wheel", handlePinch, { passive: false });
    return () => {
      element.removeEventListener("wheel", handlePinch);
      cancelAnimationFrame(pinchFrame.current);
      window.clearTimeout(pinchCommitTimer.current);
      pinchFrame.current = 0;
      pinchCommitTimer.current = 0;
      pinchDelta.current = 0;
    };
  }, [pagesRef, scrollRef]);

  return { zoom, pageWidth, liveResizeScale, setZoom: setCenteredZoom };
}
