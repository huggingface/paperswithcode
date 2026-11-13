/**
 * Global ⌘K search overlay.
 *
 * Debounced server-side search across papers, tasks, methods, benchmarks,
 * authors, and organizations.
 */

import React, { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import LatexTitle from "@/components/LatexTitle";
import { catalogQueries, ONE_MINUTE, paperQueries } from "@/lib/api/queries";
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
  const canSearch = debouncedQuery.trim().length >= TYPEAHEAD_MIN_CHARS;
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

  // Every source shares these options; results stay fresh for a minute of typing.
  const search = { enabled: open && canSearch, staleTime: ONE_MINUTE, retry: false } as const;
  const papersQ = useQuery({ ...paperQueries.search(debouncedQuery, PAPER_PAGE_SIZE), ...search });
  const tasksQ = useQuery({ ...catalogQueries.taskList({ q: debouncedQuery, page_size: 6 }), ...search });
  const methodsQ = useQuery({ ...catalogQueries.methodList({ q: debouncedQuery, page_size: 6 }), ...search });
  const benchmarksQ = useQuery({ ...catalogQueries.datasetList({ q: debouncedQuery, page_size: 6 }), ...search });
  const authorsQ = useQuery({ ...paperQueries.authorSearch(debouncedQuery, ENTITY_PAGE_SIZE), ...search });
  const organizationsQ = useQuery({
    ...catalogQueries.organizationSearch(debouncedQuery, ENTITY_PAGE_SIZE),
    ...search,
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
  // result links below open with Tab + Enter.
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
                  <Link
                    key={t.id}
                    className="search-result-tag"
                    to={`/tasks/${t.slug}`}
                    onClick={onClose}
                  >
                    <span
                      className="dot"
                      style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot }}
                    ></span>
                    <span className="name">{displayTaskName(t.name, t.slug)}</span>
                    {t.paper_count != null && <span className="count">{t.paper_count} papers</span>}
                  </Link>
                );
              })}
            </>
          )}
          {matchedMethods.length > 0 && (
            <>
              <div className="search-section-label">Methods · {matchedMethods.length}</div>
              {matchedMethods.map((m) => (
                <Link
                  key={m.id}
                  className="search-result-tag"
                  to={`/methods/${m.slug || m.id}`}
                  onClick={onClose}
                >
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>{m.name}</span>
                  {m.paper_count != null && <span className="count">{m.paper_count} papers</span>}
                </Link>
              ))}
            </>
          )}
          {matchedBenchmarks.length > 0 && (
            <>
              <div className="search-section-label">Benchmarks · {matchedBenchmarks.length}</div>
              {matchedBenchmarks.map((d) => (
                <Link
                  key={d.id}
                  className="search-result-tag"
                  to={`/benchmark/${d.slug || d.id}`}
                  onClick={onClose}
                >
                  <span className="name">{d.name}</span>
                  {d.paper_count != null && d.paper_count > 0 && (
                    <span className="count">{d.paper_count} entries</span>
                  )}
                </Link>
              ))}
            </>
          )}
          {matchedAuthors.length > 0 && (
            <>
              <div className="search-section-label">Authors · {matchedAuthors.length}</div>
              {matchedAuthors.map((a) => (
                <Link
                  key={a.id}
                  className="search-result-tag"
                  to={`/authors/${a.id}`}
                  onClick={onClose}
                >
                  <span className="name">{a.full_name}</span>
                  {a.hf_username && <span className="handle">@{a.hf_username}</span>}
                  {a.paper_count > 0 && <span className="count">{a.paper_count} papers</span>}
                </Link>
              ))}
            </>
          )}
          {matchedOrganizations.length > 0 && (
            <>
              <div className="search-section-label">
                Organizations · {matchedOrganizations.length}
              </div>
              {matchedOrganizations.map((o) => (
                <Link
                  key={o.id}
                  className="search-result-tag"
                  to={`/orgs/${o.slug}`}
                  onClick={onClose}
                >
                  {o.logo_url && <img className="logo" src={o.logo_url} alt="" loading="lazy" />}
                  <span className="name">{o.name}</span>
                  {o.paper_count != null && o.paper_count > 0 && (
                    <span className="count">{o.paper_count} papers</span>
                  )}
                </Link>
              ))}
            </>
          )}
          {matchedPapers.length > 0 && (
            <>
              <div className="search-section-label">Papers · {matchedPapers.length}</div>
              {matchedPapers.map((p) => (
                <Link
                  key={p.id}
                  className="search-result"
                  to={`/paper/${p.arxiv_id || p.id}`}
                  onClick={onClose}
                >
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
                </Link>
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
