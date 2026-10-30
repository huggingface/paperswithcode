import { useEffect } from "react";

/** Scroll to the URL hash target once the sections it may point at have rendered. */
export function useHashScrollOnReady(ready: boolean) {
  useEffect(() => {
    if (!ready || !window.location.hash) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [ready]);
}
