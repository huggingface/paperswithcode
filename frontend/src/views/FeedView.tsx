import ResearchFeedTabs from "@/components/ResearchFeedTabs";
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PaperCard } from "@/components";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { ArrowUpIcon } from "@/components/chat/icons";
import ModelPicker from "@/components/chat/ModelPicker";
import ReasoningEffortPicker from "@/components/chat/ReasoningEffortPicker";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import WebSearchToggle from "@/components/chat/WebSearchToggle";
import { chatApi } from "@/lib/api/chat";
import { catalogApi } from "@/lib/api/catalog";
import {
  CANONICAL_CHAT_URL,
  isChatEnabled,
  isChatMirror,
  isStagingEnvironment,
} from "@/lib/apiUrl";
import type { ChatDraft, ReasoningEffort } from "@/lib/chat";
import { queueChatLaunch } from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import {
  createSession,
  DEFAULT_CHAT_MODEL,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  STAGING_FALLBACK_CHAT_MODELS,
} from "@/lib/chatSessions";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfinitePapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";
import {
  readHomepagePaperDateRange,
  withHomepagePaperDateRange,
} from "@/lib/paperDateRange";

type OrderBy = "trending" | "date_published" | "citation_count";

const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];


const PLACEHOLDER_TYPE_MS = 45;
const PLACEHOLDER_HOLD_MS = 1_800;
const PLACEHOLDER_ERASE_MS = 25;
const PLACEHOLDER_GAP_MS = 350;

const useRotatingChatPlaceholder = (active: boolean) => {
  const [placeholder, setPlaceholder] = useState(SUGGESTED_CHAT_PROMPTS[0].slice(0, 1));

  useEffect(() => {
    if (!active) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
      setPlaceholder(SUGGESTED_CHAT_PROMPTS[0]);
      return;
    }

    let promptIndex = 0;
    let characterIndex = 1;
    let erasing = false;
    let timer: number;
    setPlaceholder(SUGGESTED_CHAT_PROMPTS[0].slice(0, characterIndex));

    const tick = () => {
      const prompt = SUGGESTED_CHAT_PROMPTS[promptIndex];

      if (!erasing) {
        characterIndex += 1;
        setPlaceholder(prompt.slice(0, characterIndex));
        if (characterIndex === prompt.length) {
          erasing = true;
          timer = window.setTimeout(tick, PLACEHOLDER_HOLD_MS);
          return;
        }
        timer = window.setTimeout(tick, PLACEHOLDER_TYPE_MS);
        return;
      }

      characterIndex -= 1;
      setPlaceholder(prompt.slice(0, characterIndex));
      if (characterIndex === 0) {
        erasing = false;
        promptIndex = (promptIndex + 1) % SUGGESTED_CHAT_PROMPTS.length;
        timer = window.setTimeout(tick, PLACEHOLDER_GAP_MS);
        return;
      }
      timer = window.setTimeout(tick, PLACEHOLDER_ERASE_MS);
    };

    timer = window.setTimeout(tick, PLACEHOLDER_TYPE_MS);
    return () => window.clearTimeout(timer);
  }, [active]);

  return placeholder;
};

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

// Inline "ask the assistant" box between the feed title and the paper list.
// Submitting hands the question off to the dedicated chat page; on the Space
// mirror that page lives on the canonical site and opens in a new tab.
export const AskAssistant: React.FC = () => {
  const navigate = useNavigate();
  const mirror = isChatMirror();
  const models = isStagingEnvironment()
    ? STAGING_FALLBACK_CHAT_MODELS
    : PRODUCTION_FALLBACK_CHAT_MODELS;
  const [draft, setDraft] = useState<ChatDraft>({ text: "", paperMentions: [] });
  const question = draft.text;
  const [scrollTop, setScrollTop] = useState(0);
  const [selectedModel, setSelectedModel] = useState(DEFAULT_CHAT_MODEL);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("low");
  const [launching, setLaunching] = useState(false);
  // Set when the browser blocks the mirror's new tab, so the question survives
  // as a link the visitor can open themselves.
  const [blockedHandoffUrl, setBlockedHandoffUrl] = useState<string | null>(null);
  const placeholder = useRotatingChatPlaceholder(!question);
  const ref = useRef<HTMLTextAreaElement>(null);
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => chatApi.getAvailability(),
    retry: false,
    enabled: isChatEnabled(),
  });
  const webSearchAvailable = Boolean(availabilityQuery.data?.web_search_available);
  const paperMentionsEnabled = isChatEnabled()
    && availabilityQuery.data?.paper_mentions_enabled !== false;
  const mentions = usePaperMentions({
    draft,
    onChange: setDraft,
    enabled: paperMentionsEnabled,
    textareaRef: ref,
  });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const resize = () => {
      el.style.height = "auto";
      if (question) {
        el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
        return;
      }

      // Reserve room for the tallest rotating prompt. A one-row textarea is
      // otherwise measured from the first typed character, so wrapped prompt
      // text gets clipped on narrow screens as the animation continues.
      const visiblePlaceholder = el.placeholder;
      const promptHeight = SUGGESTED_CHAT_PROMPTS.reduce((height, prompt) => {
        el.placeholder = prompt;
        return Math.max(height, el.scrollHeight);
      }, 0);
      el.placeholder = visiblePlaceholder;
      el.style.height = `${Math.min(promptHeight, 160)}px`;
    };

    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [question]);

  const submit = async (nextDraft = draft) => {
    const q = nextDraft.text.trim();
    if (!q || launching) return;
    if (mirror) {
      const params = new URLSearchParams({ q, model: selectedModel });
      const url = `${CANONICAL_CHAT_URL}?${params}`;
      const tab = window.open(url, "_blank");
      if (!tab) {
        setBlockedHandoffUrl(url);
        return;
      }
      tab.opener = null;
      setBlockedHandoffUrl(null);
      setDraft({ text: "", paperMentions: [] });
      return;
    }
    setLaunching(true);
    queueChatLaunch(nextDraft, selectedModel, {
      webSearchEnabled: webSearchAvailable && webSearchEnabled,
      reasoningEffort,
    });
    try {
      const session = await createSession(selectedModel, reasoningEffort);
      navigate(`/chat/${session.id}`);
    } catch {
      // Anonymous users still need the chat route to begin OAuth. Network and
      // quota errors are also rendered there without losing the queued prompt.
      navigate("/chat");
    }
  };

  return (
    <>
      {!mirror && (
        <div className="ask-home-new">
          Hint: type @ to bring papers into context
        </div>
      )}
      <div className="ask-home">
        <div className="ask-home-textarea-wrap">
          <PaperMentionHighlights
            text={draft.text}
            mentions={draft.paperMentions}
            scrollTop={scrollTop}
            variant="home"
          />
          <textarea
            ref={ref}
            rows={1}
            value={question}
            placeholder={placeholder}
            aria-label="Ask the assistant"
            disabled={launching}
            onChange={(event) => mentions.updateText(event.target.value, event.target.selectionStart)}
            onSelect={(event) => mentions.refresh(event.currentTarget.selectionStart)}
            onClick={(event) => mentions.refresh(event.currentTarget.selectionStart)}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
            onBlur={(event) => {
              if (!event.relatedTarget?.closest?.(".chat-paper-picker")) window.setTimeout(mentions.close, 0);
            }}
            onKeyDown={(event) => {
              if (mentions.keyDown(event)) return;
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            role={paperMentionsEnabled ? "combobox" : undefined}
            aria-expanded={paperMentionsEnabled ? mentions.open : undefined}
            aria-controls={mentions.open ? mentions.pickerId : undefined}
            aria-activedescendant={mentions.open && mentions.results.length
              ? `${mentions.optionIdPrefix}-${mentions.activeIndex}`
              : undefined}
            aria-autocomplete={paperMentionsEnabled ? "list" : undefined}
            aria-describedby={mentions.message ? "ask-home-paper-mention-message" : undefined}
          />
        </div>
        {blockedHandoffUrl && (
          <div className="chat-paper-mention-message" role="alert">
            <a href={blockedHandoffUrl} target="_blank" rel="noreferrer">
              Open this question on paperswithcode.co
            </a>
          </div>
        )}
        {mentions.message && (
          <div id="ask-home-paper-mention-message" className="chat-paper-mention-message" role="alert">
            {mentions.message}
          </div>
        )}
        <div className="ask-home-foot">
          <div className="ask-home-provider-tools">
            <ModelPicker
              models={models}
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
            />
            {!mirror && (
              <ReasoningEffortPicker
                value={reasoningEffort}
                onChange={setReasoningEffort}
                disabled={launching}
              />
            )}
            {webSearchAvailable && (
              <WebSearchToggle
                enabled={webSearchEnabled}
                onChange={setWebSearchEnabled}
                disabled={launching}
              />
            )}
          </div>
          <button
            type="button"
            className={`chat-send${question.trim() ? " chat-send-on" : ""}`}
            onClick={() => void submit()}
            disabled={!question.trim() || launching}
            aria-label="Ask the assistant"
          >
            <ArrowUpIcon />
          </button>
        </div>
        <PaperMentionPicker
          open={mentions.open}
          query={mentions.query}
          results={mentions.results}
          activeIndex={mentions.activeIndex}
          loading={mentions.loading}
          error={mentions.error}
          onSelect={mentions.select}
          id={mentions.pickerId}
          optionIdPrefix={mentions.optionIdPrefix}
        />
      </div>
    </>
  );
};

const FeedView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const dateRange = readHomepagePaperDateRange(searchParams);
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";

  const setOrderBy = (nextOrderBy: OrderBy) => {
    const next = new URLSearchParams(searchParams);
    next.set("order_by", nextOrderBy);
    setSearchParams(next);
  };

  const setHasCode = (active: boolean) => {
    const next = new URLSearchParams(searchParams);
    if (active) next.set("has_code", "true");
    else next.delete("has_code");
    setSearchParams(next);
  };

  const setHasHfArtifacts = (active: boolean) => {
    const next = new URLSearchParams(searchParams);
    if (active) next.set("has_hf_artifacts", "true");
    else next.delete("has_hf_artifacts");
    setSearchParams(next);
  };

  // Sidebar: top tasks by paper count.
  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => catalogApi.topTasks(8),
    staleTime: 10 * 60 * 1000,
  });

  // Sidebar: tasks whose share of recent papers is rising vs their baseline.
  // Independent of Top Domains; overlapping entries appear in both sections
  // so neither list misrepresents its own signal.
  const trendingTasks = useQuery({
    queryKey: ["trending-tasks-sidebar"],
    queryFn: () => catalogApi.trendingTasks({ limit: 8, level: 0 }),
    staleTime: 10 * 60 * 1000,
  });

  const infinite = useInfinitePapers({
    page_size: 30,
    order_by: orderBy,
    order_dir: "desc",
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
  });

  const cards = useMemo(() => {
    const all = infinite.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [infinite.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "400px" });
  useEffect(() => {
    if (isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLoading = infinite.isLoading;
  const error = infinite.error;

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Trending <em>Research</em>
          </h1>
          <div className="feed-subtitle">Curated daily from arXiv and Hugging Face</div>
        </div>
      </div>

      <ResearchFeedTabs />
      <div className="layout-with-sidebar">
        <aside className="sidebar">
          <div className="sidebar-section sidebar-section-top-domains">
            <div className="sidebar-label">Top Domains</div>
            {topTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {topTasks.data?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                {task.paper_count != null && <span className="count">{task.paper_count}</span>}
              </Link>
            ))}
            <Link to="/tasks" className="sidebar-link" style={{ marginTop: 8, fontStyle: "italic" }}>
              all domains →
            </Link>
          </div>

          <div className="sidebar-section sidebar-section-trending-domains">
            <div className="sidebar-label">Trending Domains</div>
            {trendingTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {trendingTasks.data?.results?.length === 0 && !trendingTasks.isLoading && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                No domains gaining momentum right now.
              </div>
            )}
            {trendingTasks.data?.results?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                <span className="count">{task.share_lift.toFixed(1)}x</span>
              </Link>
            ))}
          </div>
        </aside>

        <div className="feed-main">
          {(isChatEnabled() || isChatMirror()) && (
            <div className="feed-chat">
              <AskAssistant />
            </div>
          )}

          <div className="feed-content">
            <div className="sort-bar home-feed-sort-bar">
              <div className="paper-feed-toolbar-controls">
                <div className="sort-options">
                  {SORT_OPTIONS.map(([k, l]) => (
                    <button
                      key={k}
                      className={`sort-btn ${orderBy === k ? "active" : ""}`}
                      onClick={() => setOrderBy(k)}
                    >
                      {l}
                    </button>
                  ))}
                </div>
                <PaperFeedFilters
                  hasCode={hasCode}
                  hasHfArtifacts={hasHfArtifacts}
                  onHasCodeChange={setHasCode}
                  onHasHfArtifactsChange={setHasHfArtifacts}
                />
              </div>
              <PaperDateFilter
                startDate={dateRange.startDate}
                endDate={dateRange.endDate}
                onChange={(value) => setSearchParams(withHomepagePaperDateRange(searchParams, value))}
              />
            </div>

            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
              </Alert>
            )}

            {isLoading ? (
              <div className="paper-list">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="paper-card">
                    <div className="paper-thumb-wrap">
                      <Skeleton className="paper-thumb-skeleton" />
                    </div>
                    <div className="paper-body" style={{ flex: 1, gap: 12 }}>
                      <Skeleton className="h-6 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-12 w-full" />
                    </div>
                  </div>
                ))}
              </div>
            ) : cards.length === 0 ? (
              <div className="no-results">No papers in this window.</div>
            ) : (
              <>
                <div className="paper-list">
                  {cards.map((p, i) => (
                    <PaperCard key={p.id} paper={p} rank={i + 1} />
                  ))}
                </div>
                <div ref={sentinelRef} style={{ height: 1 }} />
                {infinite.isFetchingNextPage && (
                  <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
                    Loading more…
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FeedView;
