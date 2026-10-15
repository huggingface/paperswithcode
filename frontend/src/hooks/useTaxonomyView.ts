import { useLocation, useNavigate } from "react-router-dom";

export type TaxonomyView = "trending" | "all";

/**
 * Trending is the default view of the tasks and methods directories.
 * `?view=all` or an `#area-…` anchor (linked from detail pages) opens the
 * full area-by-area listing instead.
 */
export function useTaxonomyView(): [TaxonomyView, (view: TaxonomyView) => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const view: TaxonomyView =
    params.get("view") === "all" || location.hash.startsWith("#area-") ? "all" : "trending";
  const setView = (next: TaxonomyView) => {
    const nextParams = new URLSearchParams(location.search);
    if (next === "all") nextParams.set("view", "all");
    else nextParams.delete("view");
    const search = nextParams.toString();
    navigate({ pathname: location.pathname, search: search ? `?${search}` : "" });
  };
  return [view, setView];
}
