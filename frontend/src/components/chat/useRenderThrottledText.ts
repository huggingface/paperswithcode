import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** Longest a streaming answer may lag behind the text that has arrived. */
const MAX_WAIT_MS = 1_000;
/** Wait this many times the last render's cost before rendering again. */
const RENDER_COST_MULTIPLIER = 2;

/**
 * Throttle streaming text by how long the last render took, so the Markdown
 * parse of a long answer can't fall behind the stream: cheap renders update
 * on every change, costly ones at most every 2× their duration (≤ 1 s).
 * Text arriving meanwhile is merged into the next update. Without
 * `throttle`, the latest text passes straight through.
 */
export function useRenderThrottledText(text: string, throttle: boolean): string {
  const [shown, setShown] = useState(text);
  const renderStartedAtRef = useRef(performance.now());
  const nextUpdateAtRef = useRef(0);

  useLayoutEffect(() => {
    const now = performance.now();
    nextUpdateAtRef.current = now
      + Math.min(MAX_WAIT_MS, (now - renderStartedAtRef.current) * RENDER_COST_MULTIPLIER);
  }, [shown]);

  useEffect(() => {
    if (!throttle || text === shown) return;
    const update = () => {
      renderStartedAtRef.current = performance.now();
      setShown(text);
    };
    const timer = window.setTimeout(update, Math.max(0, nextUpdateAtRef.current - performance.now()));
    return () => window.clearTimeout(timer);
  }, [text, throttle, shown]);

  return throttle ? shown : text;
}
