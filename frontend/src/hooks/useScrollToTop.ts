import { useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scroll the window to the top whenever the pathname changes. Query-string
 * updates represent in-page state such as feed filters and sorting, so they
 * deliberately preserve the current scroll position.
 *
 * Skipped when the URL carries a hash (e.g. `/paper/98456#results`) so route
 * navigation doesn't fight intentional deep links: the page's own hash-scroll
 * logic is responsible for landing on the anchored section instead.
 */
export function useScrollToTop(): void {
  const { pathname, hash } = useLocation();
  useLayoutEffect(() => {
    if (hash) return;
    // Override the global smooth-scroll CSS: a route reset must finish before
    // paint, not leave the new page under the sticky header mid-animation.
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname, hash]);
}
