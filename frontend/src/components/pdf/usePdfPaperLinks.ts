import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import type { PdfLinkAnnotation } from "./pdfCitationLinks";
import type { PdfPaperLinkTarget } from "./PdfPaperLink";

// onResolved receives every route id about to become hoverable so callers can
// warm preview cards before the pointer arrives.
export function usePdfPaperLinks(ref: RefObject<HTMLDivElement>, visible: boolean, resolveCitation?: (annotation: PdfLinkAnnotation) => Promise<string | null>, onResolved?: (routeIds: string[]) => void) {
  const annotationsRef = useRef<PdfLinkAnnotation[]>([]);
  const generation = useRef(0);
  const [paperLinks, setPaperLinks] = useState<PdfPaperLinkTarget[]>([]);
  useEffect(() => () => { generation.current += 1; }, []);
  const onAnnotations = useCallback((annotations: PdfLinkAnnotation[]) => {
    annotationsRef.current = annotations;
  }, []);
  const onAnnotationRender = useCallback(() => {
    const current = ++generation.current;
    setPaperLinks([]);
    if (!resolveCitation) return;
    const anchors = new Map(Array.from(ref.current?.querySelectorAll<HTMLAnchorElement>("[data-annotation-id] a:not(.pdf-paper-preview-link)") ?? [])
      .map(anchor => [anchor.parentElement?.dataset.annotationId, anchor]));
    void Promise.all(annotationsRef.current.map(async (annotation): Promise<PdfPaperLinkTarget | null> => {
      const anchor = anchors.get(annotation.id);
      if (!anchor) return null;
      const routeId = await resolveCitation(annotation).catch(() => null);
      return routeId ? { anchor, routeId, internal: !annotation.url, dest: typeof annotation.dest === 'string' ? annotation.dest : undefined } : null;
    })).then(links => {
      if (generation.current !== current) return;
      const connected = links.filter((link): link is PdfPaperLinkTarget => link !== null && link.anchor.isConnected);
      if (connected.length) onResolved?.([...new Set(connected.map(link => link.routeId))]);
      setPaperLinks(connected);
    });
  }, [onResolved, ref, resolveCitation]);
  useEffect(() => {
    const root = ref.current;
    if (!root || !visible || !resolveCitation) return;
    // PDF.js appends annotation sections asynchronously, after React-PDF's
    // render-success callback. Observe those sections, not our portal anchors.
    let frame = requestAnimationFrame(onAnnotationRender);
    const observer = new MutationObserver(records => {
      if (!records.some(record => [...record.addedNodes].some(node => node instanceof Element && node.matches('.linkAnnotation')))) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(onAnnotationRender);
    });
    observer.observe(root, { childList: true, subtree: true });
    return () => { observer.disconnect(); cancelAnimationFrame(frame); generation.current += 1; };
  }, [onAnnotationRender, ref, resolveCitation, visible]);
  return { paperLinks, onAnnotations };
}
