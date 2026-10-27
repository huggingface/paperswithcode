import { paperQueryKeys } from "@/lib/paperQueryKeys";
/**
 * Global ⌘K search overlay.
 *
 * Debounced server-side search across papers, tasks, methods, benchmarks,
 * authors, and organizations.
 */

import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import LatexTitle from "@/components/LatexTitle";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isChatEnabled } from "@/lib/apiUrl";
import { useDebounce } from "@/hooks/useDebounce";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";

interface SearchOverlayProps {
  open: boolean;
  onClose: () => void;
}

const PAPER_PAGE_SIZE = 10;
const ENTITY_PAGE_SIZE = 6;
// Every debounced keystroke fans out to six catalog requests, three of which
// share nginx's per-IP search limit (60/min, burst 20). A slower debounce, a
// three-character minimum, and no retries keep a fast typist under it; a 429
// while typing is not worth a second request for the same prefix.
const TYPEAHEAD_DEBOUNCE_MS = 350;
const TYPEAHEAD_MIN_CHARS = 3;

const SearchOverlay: React.FC<SearchOverlayProps> = ({ open, onClose }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [query, setQuery] = React.useState("");
  const debouncedQuery = useDebounce(query, TYPEAHEAD_DEBOUNCE_MS);
  const trimmedQuery = query.trim();
  const canSearch = debouncedQuery.length >= TYPEAHEAD_MIN_CHARS;
  const chatEnabled = isChatEnabled();

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    // Consume Escape before keyboard shortcuts in the page beneath the overlay.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  const papersQ = useQuery({
    queryKey: [...paperQueryKeys.feeds.searchOverlay, debouncedQuery],
    queryFn: () => papersApi.search(debouncedQuery, 1, PAPER_PAGE_SIZE),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  const tasksQ = useQuery({
    queryKey: ["search-tasks", debouncedQuery],
    queryFn: () => catalogApi.listTasks({ q: debouncedQuery, page_size: 6 }),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  const methodsQ = useQuery({
    queryKey: ["search-methods", debouncedQuery],
    queryFn: () => catalogApi.listMethods({ q: debouncedQuery, page_size: 6 }),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  const benchmarksQ = useQuery({
    queryKey: ["search-benchmarks", debouncedQuery],
    queryFn: () =>
      catalogApi.listDatasets({
        q: debouncedQuery,
        page_size: 6,
      }),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  const authorsQ = useQuery({
    queryKey: ["search-authors", debouncedQuery],
    queryFn: () => papersApi.searchAuthors(debouncedQuery, ENTITY_PAGE_SIZE),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  const organizationsQ = useQuery({
    queryKey: ["search-organizations", debouncedQuery],
    queryFn: () => catalogApi.searchOrganizations(debouncedQuery, ENTITY_PAGE_SIZE),
    enabled: open && canSearch,
    staleTime: 60_000,
    retry: false,
  });

  if (!open) return null;

  const matchedTasks = tasksQ.data?.results || [];
  const matchedMethods = methodsQ.data?.results || [];
  const matchedBenchmarks = benchmarksQ.data?.results || [];
  const matchedAuthors = authorsQ.data?.results || [];
  const matchedOrganizations = organizationsQ.data?.results || [];
  const matchedPapers = papersQ.data?.results || [];
  const isLoading =
    papersQ.isFetching ||
    tasksQ.isFetching ||
    methodsQ.isFetching ||
    benchmarksQ.isFetching ||
    authorsQ.isFetching ||
    organizationsQ.isFetching;
  const hasResults =
    matchedTasks.length ||
    matchedPapers.length ||
    matchedMethods.length ||
    matchedBenchmarks.length ||
    matchedAuthors.length ||
    matchedOrganizations.length;

  const go = (path: string) => {
    onClose();
    navigate(path);
  };

  // Enter hands the query to the AI assistant on /chat; browsing the live
  // results below remains click/tab-driven as before.
  const askAssistant = () => {
    const q = query.trim();
    if (q) go(`/chat?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="search-modal-input"
          placeholder="Search papers, tasks, methods, benchmarks, authors, or organizations…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (chatEnabled && e.key === "Enter") {
              e.preventDefault();
              askAssistant();
            }
          }}
        />
        <div className="search-results">
          {chatEnabled && query.trim() && (
            <button type="button" className="search-ask-row" onClick={askAssistant}>
              <span className="search-ask-chip">assistant</span>
              <span className="search-ask-text">Ask: “{query.trim()}”</span>
              <kbd>↵</kbd>
            </button>
          )}
          {!debouncedQuery && (
            <div className="search-empty">
              Try “diffusion”, “object detection”, or an arXiv id.
              {chatEnabled && (
                <span className="search-empty-sub">Press Enter to ask the assistant</span>
              )}
            </div>
          )}
          {debouncedQuery && !canSearch && (
            <div className="search-empty">
              Keep typing: results appear from {TYPEAHEAD_MIN_CHARS} characters.
            </div>
          )}
          {canSearch && !isLoading && !hasResults && (
            <div className="search-empty">No matches for "{query}"</div>
          )}
          {matchedTasks.length > 0 && (
            <>
              <div className="search-section-label">Tasks · {matchedTasks.length}</div>
              {matchedTasks.map((t) => {
                const c = chipColors(hueFromSlug(t.slug || ""));
                return (
                  <div
                    key={t.id}
                    className="search-result-tag"
                    onClick={() => go(`/tasks/${t.slug}`)}
                  >
                    <span
                      className="dot"
                      style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot }}
                    ></span>
                    <span className="name">{displayTaskName(t.name, t.slug)}</span>
                    {t.paper_count != null && <span className="count">{t.paper_count} papers</span>}
                  </div>
                );
              })}
            </>
          )}
          {matchedMethods.length > 0 && (
            <>
              <div className="search-section-label">Methods · {matchedMethods.length}</div>
              {matchedMethods.map((m) => (
                <div
                  key={m.id}
                  className="search-result-tag"
                  onClick={() => go(`/methods/${m.slug || m.id}`)}
                >
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>{m.name}</span>
                  {m.paper_count != null && <span className="count">{m.paper_count} papers</span>}
                </div>
              ))}
            </>
          )}
          {matchedBenchmarks.length > 0 && (
            <>
              <div className="search-section-label">Benchmarks · {matchedBenchmarks.length}</div>
              {matchedBenchmarks.map((d) => (
                <div
                  key={d.id}
                  className="search-result-tag"
                  onClick={() => go(`/benchmark/${d.slug || d.id}`)}
                >
                  <span className="name">{d.name}</span>
                  {d.paper_count != null && d.paper_count > 0 && (
                    <span className="count">{d.paper_count} entries</span>
                  )}
                </div>
              ))}
            </>
          )}
          {matchedAuthors.length > 0 && (
            <>
              <div className="search-section-label">Authors · {matchedAuthors.length}</div>
              {matchedAuthors.map((a) => (
                <div
                  key={a.id}
                  className="search-result-tag"
                  onClick={() => go(`/authors/${a.id}`)}
                >
                  <span className="name">{a.full_name}</span>
                  {a.hf_username && <span className="handle">@{a.hf_username}</span>}
                  {a.paper_count > 0 && <span className="count">{a.paper_count} papers</span>}
                </div>
              ))}
            </>
          )}
          {matchedOrganizations.length > 0 && (
            <>
              <div className="search-section-label">
                Organizations · {matchedOrganizations.length}
              </div>
              {matchedOrganizations.map((o) => (
                <div
                  key={o.id}
                  className="search-result-tag"
                  onClick={() => go(`/orgs/${o.slug}`)}
                >
                  {o.logo_url && <img className="logo" src={o.logo_url} alt="" loading="lazy" />}
                  <span className="name">{o.name}</span>
                  {o.paper_count != null && o.paper_count > 0 && (
                    <span className="count">{o.paper_count} papers</span>
                  )}
                </div>
              ))}
            </>
          )}
          {matchedPapers.length > 0 && (
            <>
              <div className="search-section-label">Papers · {matchedPapers.length}</div>
              {matchedPapers.map((p) => (
                <div key={p.id} className="search-result" onClick={() => go(`/paper/${p.arxiv_id || p.id}`)}>
                  <div className="search-result-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="search-result-meta">
                    <span>{p.arxiv_id ? `arXiv:${p.arxiv_id}` : "External resource"}</span>
                    {p.authors?.[0] && (
                      <>
                        <span>·</span>
                        <span>{p.authors[0]}{p.authors.length > 1 ? " et al." : ""}</span>
                      </>
                    )}
                    {p.citation_count != null && (
                      <>
                        <span>·</span>
                        <span>↑ {p.citation_count.toLocaleString()}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
          {trimmedQuery.length >= TYPEAHEAD_MIN_CHARS && (
            <button
              type="button"
              className="search-view-all-row"
              onClick={() => go(`/papers?search=${encodeURIComponent(trimmedQuery)}`)}
            >
              View all paper results for “{trimmedQuery}”
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchOverlay;
