import { useEffect, useRef } from "react";

import type { PaperSelectionDraft } from "@/lib/chat";
import {
  commitPdfSelection,
  paperSelectionFingerprint,
} from "@/lib/paperSelection";

const FALLBACK_DEBOUNCE_MS = 280;
const NAV_KEYS = new Set([
  "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown", "A",
]);

export interface UsePdfSelectionOptions {
  enabled: boolean;
  pagesRoot: React.RefObject<HTMLElement | null>;
  routeId: string;
  paperVersion: string;
  numPages?: number;
  onSelect?: (selection: PaperSelectionDraft) => void;
  onError?: (message: string) => void;
}

export function usePdfSelection({
  enabled,
  pagesRoot,
  routeId,
  paperVersion,
  numPages,
  onSelect,
  onError,
}: UsePdfSelectionOptions) {
  const pointerSelecting = useRef(false);
  const selectionCanceled = useRef(false);
  const lastFingerprint = useRef("");
  const fallbackTimer = useRef(0);
  const commitFrame = useRef(0);
  const fallbackSignature = useRef("");
  const onSelectRef = useRef(onSelect);
  const onErrorRef = useRef(onError);
  onSelectRef.current = onSelect;
  onErrorRef.current = onError;

  useEffect(() => {
    pointerSelecting.current = false;
    selectionCanceled.current = false;
    lastFingerprint.current = "";
    fallbackSignature.current = "";
    window.clearTimeout(fallbackTimer.current);
    cancelAnimationFrame(commitFrame.current);
    commitFrame.current = 0;
  }, [routeId, paperVersion]);

  useEffect(() => {
    if (!enabled) {
      pointerSelecting.current = false;
      selectionCanceled.current = false;
      window.clearTimeout(fallbackTimer.current);
      cancelAnimationFrame(commitFrame.current);
      commitFrame.current = 0;
      return;
    }

    const commit = () => {
      const result = commitPdfSelection({
        selection: window.getSelection(),
        pagesRoot: pagesRoot.current,
        routeId,
        paperVersion,
        numPages,
      });
      if (!result.ok) {
        if (result.error) onErrorRef.current?.(result.error);
        return;
      }
      const fingerprint = paperSelectionFingerprint(result.selection);
      if (fingerprint === lastFingerprint.current) return;
      lastFingerprint.current = fingerprint;
      onSelectRef.current?.(result.selection);
    };

    const queueCommit = () => {
      window.clearTimeout(fallbackTimer.current);
      cancelAnimationFrame(commitFrame.current);
      commitFrame.current = requestAnimationFrame(() => {
        commitFrame.current = 0;
        commit();
      });
    };

    const onPointerDown = (event: PointerEvent) => {
      const root = pagesRoot.current;
      if (!root || !event.isPrimary) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      if (!(event.target instanceof Node) || !root.contains(event.target)) return;
      pointerSelecting.current = true;
      selectionCanceled.current = false;
      lastFingerprint.current = "";
      window.clearTimeout(fallbackTimer.current);
      cancelAnimationFrame(commitFrame.current);
      commitFrame.current = 0;
    };

    const onPointerUp = (event: PointerEvent) => {
      if (!pointerSelecting.current || !event.isPrimary) return;
      pointerSelecting.current = false;
      queueCommit();
    };

    const onPointerCancel = (event: PointerEvent) => {
      if (!pointerSelecting.current || !event.isPrimary) return;
      pointerSelecting.current = false;
      selectionCanceled.current = true;
      fallbackSignature.current = "";
      window.clearTimeout(fallbackTimer.current);
      cancelAnimationFrame(commitFrame.current);
      commitFrame.current = 0;
    };

    const onKeyUp = (event: KeyboardEvent) => {
      const root = pagesRoot.current;
      if (!root || pointerSelecting.current) return;
      const inLayer = event.target instanceof Node && Boolean(
        (event.target instanceof Element ? event.target : event.target.parentElement)
          ?.closest?.(".textLayer, .reader-web-document")
        && root.contains(event.target),
      );
      if (!inLayer) return;
      const isSelectAll = (event.key === "a" || event.key === "A") && (event.metaKey || event.ctrlKey);
      if (event.shiftKey || NAV_KEYS.has(event.key) || isSelectAll) {
        selectionCanceled.current = false;
        lastFingerprint.current = "";
        queueCommit();
      }
    };

    const onSelectionChange = () => {
      if (pointerSelecting.current || selectionCanceled.current) return;
      const selection = window.getSelection();
      const signature = selection && selection.rangeCount === 1
        ? `${selection.toString()}\0${selection.anchorNode ? 1 : 0}\0${selection.focusNode ? 1 : 0}`
        : "";
      fallbackSignature.current = signature;
      window.clearTimeout(fallbackTimer.current);
      fallbackTimer.current = window.setTimeout(() => {
        if (fallbackSignature.current !== signature) return;
        commit();
      }, FALLBACK_DEBOUNCE_MS);
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointerup", onPointerUp, true);
    document.addEventListener("pointercancel", onPointerCancel, true);
    document.addEventListener("keyup", onKeyUp, true);
    document.addEventListener("selectionchange", onSelectionChange);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("pointerup", onPointerUp, true);
      document.removeEventListener("pointercancel", onPointerCancel, true);
      document.removeEventListener("keyup", onKeyUp, true);
      document.removeEventListener("selectionchange", onSelectionChange);
      window.clearTimeout(fallbackTimer.current);
      cancelAnimationFrame(commitFrame.current);
    };
  }, [enabled, numPages, pagesRoot, paperVersion, routeId]);
}
