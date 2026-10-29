import FollowingIntro from "@/components/FollowingIntro";
import TopicDialog from "@/components/TopicDialog";
import { isAuthDisabled } from "@/lib/apiUrl";
import { clearPendingTopic, readPendingFollows, readPendingTopic, useSaveFollows, useSaveTopic } from "@/lib/researchTopic";
import { useOptionalAuth } from "@/lib/authContext";
import { researchApi, type FollowKind } from "@/lib/api/research";
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PaperCard } from "@/components";
import { McpShowcase } from "@/components/McpShowcase";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { ArrowUpIcon } from "@/components/chat/icons";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { completedScrollHeight, isCompletionKey, useChatCompletion } from "@/components/chat/useChatCompletion";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import { chatApi } from "@/lib/api/chat";
import { catalogApi } from "@/lib/api/catalog";
import {
  CANONICAL_CHAT_URL,
  isChatEnabled,
  isChatMirror,
} from "@/lib/apiUrl";
import type { ChatDraft } from "@/lib/chat";
import { queueChatLaunch } from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import {
  createSession,
  DEFAULT_CHAT_MODEL,
} from "@/lib/chatSessions";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfinitePapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  readHomepagePaperDateRange,
  withHomepagePaperDateRange,
} from "@/lib/paperDateRange";


const PLACEHOLDER_TYPE_MS = 45;
const PLACEHOLDER_HOLD_MS = 1_800;
const PLACEHOLDER_ERASE_MS = 25;
const PLACEHOLDER_GAP_MS = 350;

// Returns the animated placeholder and the full prompt it is showing, which Tab
// accepts into the empty chat box.
const useRotatingChatPlaceholder = (active: boolean) => {
  const [placeholder, setPlaceholder] = useState(SUGGESTED_CHAT_PROMPTS[0].slice(0, 1));
  const [promptIndex, setPromptIndex] = useState(0);

  useEffect(() => {
    if (!active) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) {
      setPlaceholder(SUGGESTED_CHAT_PROMPTS[0]);
      setPromptIndex(0);
      return;
    }

    let promptIndex = 0;
    let characterIndex = 1;
    let erasing = false;
    let timer: number;
    setPlaceholder(SUGGESTED_CHAT_PROMPTS[0].slice(0, characterIndex));
    setPromptIndex(0);

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
        setPromptIndex(promptIndex);
        timer = window.setTimeout(tick, PLACEHOLDER_GAP_MS);
        return;
      }
      timer = window.setTimeout(tick, PLACEHOLDER_ERASE_MS);
    };

    timer = window.setTimeout(tick, PLACEHOLDER_TYPE_MS);
    return () => window.clearTimeout(timer);
  }, [active]);

  return { placeholder, prompt: SUGGESTED_CHAT_PROMPTS[promptIndex] };
};

// Inline "ask the assistant" box between the feed title and the paper list.
// Submitting hands the question off to the dedicated chat page; on the Space
// mirror that page lives on the canonical site and opens in a new tab.
export const AskAssistant: React.FC = () => {
  const navigate = useNavigate();
  const mirror = isChatMirror();
  const [draft, setDraft] = useState<ChatDraft>({ text: "", paperMentions: [] });
  const question = draft.text;
  const [scrollTop, setScrollTop] = useState(0);
  const [launching, setLaunching] = useState(false);
  // Set when the browser blocks the mirror's new tab, so the question survives
  // as a link the visitor can open themselves.
  const [blockedHandoffUrl, setBlockedHandoffUrl] = useState<string | null>(null);
  const { placeholder, prompt: placeholderPrompt } = useRotatingChatPlaceholder(!question);
  const ref = useRef<HTMLTextAreaElement>(null);
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => chatApi.getAvailability(),
    retry: false,
    enabled: isChatEnabled(),
  });
  const paperMentionsEnabled = isChatEnabled()
    && availabilityQuery.data?.paper_mentions_enabled !== false;
  const mentions = usePaperMentions({
    draft,
    onChange: setDraft,
    enabled: paperMentionsEnabled,
    textareaRef: ref,
  });
  const typedCompletion = useChatCompletion(draft, mentions.open);
  // Tab accepts the shown suggestion: the whole prompt in an empty box, or the
  // rest of what the visitor has started typing.
  const completion = question ? typedCompletion.completion : placeholderPrompt;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const resize = () => {
      el.style.height = "auto";
      if (question) {
        el.style.height = `${Math.min(completedScrollHeight(el), 160)}px`;
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
  }, [question, completion]);

  const submit = async (nextDraft = draft) => {
    const q = nextDraft.text.trim();
    if (!q || launching) return;
    if (mirror) {
      const params = new URLSearchParams({ q, model: DEFAULT_CHAT_MODEL });
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
    queueChatLaunch(nextDraft, DEFAULT_CHAT_MODEL);
    try {
      const session = await createSession(DEFAULT_CHAT_MODEL);
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
          Hint: type @ to bring papers into context, or press Tab to use a suggestion
        </div>
      )}
      <div className="ask-home">
        <div className="ask-home-row">
          <div className="ask-home-textarea-wrap">
            <PaperMentionHighlights
              text={draft.text}
              mentions={draft.paperMentions}
              scrollTop={scrollTop}
              variant="home"
              completion={question ? completion : ""}
            />
            <textarea
              ref={ref}
              rows={1}
              value={question}
              placeholder={placeholder}
              aria-label="Ask the assistant"
              disabled={launching}
              onChange={(event) => {
                mentions.updateText(event.target.value, event.target.selectionStart);
                typedCompletion.trackCaret(event.target);
              }}
              onSelect={(event) => {
                mentions.refresh(event.currentTarget.selectionStart);
                typedCompletion.trackCaret(event.currentTarget);
              }}
              onClick={(event) => {
                mentions.refresh(event.currentTarget.selectionStart);
                typedCompletion.trackCaret(event.currentTarget);
              }}
              onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
              onBlur={(event) => {
                if (!event.relatedTarget?.closest?.(".chat-paper-picker")) window.setTimeout(mentions.close, 0);
              }}
              onKeyDown={(event) => {
                if (mentions.keyDown(event)) return;
                if (isCompletionKey(event) && completion) {
                  event.preventDefault();
                  const text = question + completion;
                  mentions.updateText(text, text.length);
                  window.requestAnimationFrame(() => ref.current?.setSelectionRange(text.length, text.length));
                  return;
                }
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

const FOLLOW_KIND_LABELS: Record<FollowKind, string> = {
  task: "Tasks",
  method: "Methods",
  benchmark: "Benchmarks",
  author: "Authors",
  organization: "Orgs",
};
const FOLLOW_KIND_ORDER = Object.keys(FOLLOW_KIND_LABELS) as FollowKind[];

const FeedView: React.FC<{ following?: boolean }> = ({ following = false }) => {
  const navigate = useNavigate();
  const auth = useOptionalAuth();
  const user = auth?.user;
  const [searchParams, setSearchParams] = useSearchParams();
  // Following defaults to its 30-day match window; the other tabs default to a week.
  const dateRange = readHomepagePaperDateRange(searchParams, undefined, following ? "month" : "week");

  // The home feed only offers trending and following; newest and most cited
  // stay on the other paper feeds.
  const showTrending = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("order_by");
    next.delete("only");
    const query = next.toString();
    navigate(query ? `/?${query}` : "/");
  };

  const topicFilterHref = (active: boolean) => {
    const next = new URLSearchParams(searchParams);
    if (active) next.set("only", "topic");
    else next.delete("only");
    const query = next.toString();
    return query ? `/following?${query}` : "/following";
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

  const publicFeed = useInfinitePapers({
    enabled: !following,
    page_size: 30,
    order_by: "trending",
    order_dir: "desc",
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    include_resources: true,
  });

  const topicOnly = following && searchParams.get("only") === "topic";
  const followingFilters = { ...dateRange, topicOnly };
  const followedFeed = useInfiniteQuery({
    queryKey: ["research-feed", user?.hf_subject, followingFilters],
    queryFn: ({ pageParam }) => researchApi.following(pageParam, followingFilters),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => last.length === 40 ? pages.length * 40 : undefined,
    enabled: following && !!user,
  });
  const follows = useQuery({
    queryKey: ["research-follows", user?.hf_subject],
    queryFn: researchApi.follows,
    enabled: following && !!user,
  });
  const topic = useQuery({
    queryKey: ["research-topic", user?.hf_subject],
    queryFn: researchApi.topic,
    enabled: following && !!user,
    refetchInterval: query => query.state.data && ["pending", "running"].includes(query.state.data.status) ? 10000 : false,
  });
  const topicBuilding = !!topic.data && ["pending", "running"].includes(topic.data.status);
  const topicName = topic.data ? topic.data.label ?? topic.data.text : "";
  const [editingTopic, setEditingTopic] = useState(false);
  // Refresh the feed once a new topic's backfill finishes.
  const queryClient = useQueryClient();
  const wasBuilding = useRef(false);
  useEffect(() => {
    if (wasBuilding.current && !topicBuilding) {
      void queryClient.invalidateQueries({ queryKey: ["research-feed", user?.hf_subject] });
    }
    wasBuilding.current = topicBuilding;
  }, [topicBuilding, queryClient, user?.hf_subject]);
  const noFollows = following && !!user && follows.data?.length === 0 && topic.isSuccess && !topic.data;
  const showIntro = (following && !auth?.isLoading && !user) || noFollows;
  const canBuildFeed = !!user || !isAuthDisabled();
  // The pop-up opens on its own only when the intro first shows to a visitor who arrived without follows:
  // not after a removal, and not while saving what a guest picked before signing in, which may finish
  // before follows reload. It lives here rather than in the intro so it stays open once the first save lands.
  const [hadFollows, setHadFollows] = useState(false);
  const [restoringPicks] = useState(() => !!readPendingTopic() || readPendingFollows().length > 0);
  const [introShown, setIntroShown] = useState(false);
  if (!hadFollows && (!!topic.data || !!follows.data?.length)) setHadFollows(true);
  if (showIntro && !introShown) {
    setIntroShown(true);
    if (canBuildFeed && !hadFollows && !restoringPicks) setEditingTopic(true);
  }
  // Save the topic a guest submitted before signing in; it stays stashed until the save succeeds.
  const pendingSave = useSaveTopic();
  const { mutate: savePendingTopic } = pendingSave;
  const pendingStarted = useRef(false);
  useEffect(() => {
    const pending = readPendingTopic();
    if (!user || !topic.isSuccess || !pending || pendingStarted.current) return;
    pendingStarted.current = true;
    if (pending === topic.data?.text) clearPendingTopic();
    else savePendingTopic(pending);
  }, [user, topic.isSuccess, topic.data, savePendingTopic]);
  // Likewise follow the tasks and methods a guest picked in the pop-up before signing in.
  const pendingFollows = useSaveFollows();
  const { mutate: savePendingFollows } = pendingFollows;
  const pendingFollowsStarted = useRef(false);
  useEffect(() => {
    const picks = readPendingFollows();
    if (!user || !picks.length || pendingFollowsStarted.current) return;
    pendingFollowsStarted.current = true;
    savePendingFollows(picks);
  }, [user, savePendingFollows]);
  const followGroups = useMemo(
    () => FOLLOW_KIND_ORDER
      .map(kind => ({ kind, follows: following ? follows.data?.filter(follow => follow.kind === kind) ?? [] : [] }))
      .filter(group => group.follows.length > 0),
    [following, follows.data],
  );
  // Keep the follows section up while auth or follows load so the domain lists never flash in.
  const showFollowsSidebar = following && (!!auth?.isLoading || (!!user && !noFollows));
  const infinite = following ? followedFeed : publicFeed;
  const cards = useMemo(() => following
    ? followedFeed.data?.pages.flatMap(page => page.map(entry => ({ ...transformPaperForCard(entry.paper), followReasons: entry.reasons }))) ?? []
    : publicFeed.data?.pages.flatMap(page => page.results.map(paper => ({ ...transformPaperForCard(paper), followReasons: undefined }))) ?? [],
  [following, followedFeed.data, publicFeed.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "400px" });
  useEffect(() => {
    if (isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLoading = infinite.isLoading || (following && auth?.isLoading);
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

      <div className="layout-with-sidebar">
        <aside className="sidebar feed-sidebar">
          {showFollowsSidebar ? (
            <div className="sidebar-section sidebar-section-follows">
              <div className="sidebar-label">You follow</div>
              {(auth?.isLoading || follows.isLoading) && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-5 w-full" />
                  ))}
                </div>
              )}
              {follows.isError && (
                <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>Couldn't load your follows.</div>
              )}
              <div className="sidebar-links">
                {topic.data && (
                  <div className={`sidebar-follow-topic ${topicOnly ? "active" : ""}`}>
                    <Link
                      to={topicFilterHref(!topicOnly)}
                      className="sidebar-link sidebar-follow-link"
                      title={topicOnly ? "Show papers from everything you follow" : `Show only papers about “${topic.data.text}”`}
                      aria-current={topicOnly ? "true" : undefined}
                    >
                      <span className="sidebar-follow-kind">Topic</span>
                      <span className="sidebar-follow-name">{topicName}</span>
                    </Link>
                    <button type="button" className="sidebar-follow-edit" aria-label="Edit topic"
                      aria-expanded={editingTopic} onClick={() => setEditingTopic(true)}>edit</button>
                  </div>
                )}
                {followGroups.map((group) => (
                  <div key={group.kind} className="sidebar-follow-group">
                    <span className="sidebar-follow-kind">{FOLLOW_KIND_LABELS[group.kind]}</span>
                    {group.follows.map((follow) => (
                      <Link key={follow.entity_id} to={follow.url} className="sidebar-link sidebar-follow-link">
                        <span className="sidebar-follow-name">{follow.name}</span>
                      </Link>
                    ))}
                  </div>
                ))}
              </div>
              <Link to="/settings" className="sidebar-follow-manage">Manage in Settings</Link>
            </div>
          ) : (
            <>
              <div className="sidebar-section sidebar-section-top-domains">
                <div className="sidebar-label">Top Domains</div>
                {topTasks.isLoading && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Skeleton key={i} className="h-5 w-full" />
                    ))}
                  </div>
                )}
                <div className="sidebar-links">
                  {topTasks.data?.map((task) => (
                    <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                      {displayTaskName(task.name, task.slug)}
                      {task.paper_count != null && <span className="count">{task.paper_count}</span>}
                    </Link>
                  ))}
                  <Link to="/tasks" className="sidebar-link sidebar-link-more">
                    all domains →
                  </Link>
                </div>
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
                <div className="sidebar-links">
                  {trendingTasks.data?.results?.map((task) => (
                    <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                      {displayTaskName(task.name, task.slug)}
                      <span className="count">{task.share_lift.toFixed(1)}x</span>
                    </Link>
                  ))}
                </div>
              </div>
            </>
          )}

          <McpShowcase />
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
                  <button className={`sort-btn ${following ? "" : "active"}`} onClick={showTrending}>trending</button>
                  <button className={`sort-btn ${following ? "active" : ""}`} onClick={() => {
                    const next = new URLSearchParams(searchParams);
                    next.delete("order_by");
                    const query = next.toString();
                    navigate(query ? `/following?${query}` : "/following");
                  }}>following</button>
                </div>
              </div>
              <PaperDateFilter
                startDate={dateRange.startDate}
                endDate={dateRange.endDate}
                onChange={(value) => setSearchParams(withHomepagePaperDateRange(searchParams, value))}
              />
            </div>

            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  Failed to load papers. <button type="button" onClick={() => void infinite.refetch()}>Try again</button>
                </AlertDescription>
              </Alert>
            )}

            {pendingSave.isError && pendingSave.variables && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  Could not follow “{pendingSave.variables}”. <button type="button" onClick={() => savePendingTopic(pendingSave.variables)}>Try again</button>
                </AlertDescription>
              </Alert>
            )}

            {pendingFollows.isError && pendingFollows.variables && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  Could not follow {pendingFollows.variables.map(pick => pick.name).join(", ")}. <button type="button" onClick={() => savePendingFollows(pendingFollows.variables)}>Try again</button>
                </AlertDescription>
              </Alert>
            )}

            {following && !!user && topic.isSuccess && !follows.isPending && !noFollows && (!topic.data ? (
              <div className="following-topic-note" role="status">
                Describe a topic in your own words, and a model adds matching new papers to this feed.{" "}
                <button type="button" className="link-button" onClick={() => setEditingTopic(true)}>Follow a topic</button>
              </div>
            ) : topicBuilding ? (
              <div className="following-topic-note" role="status">
                Showing the closest papers about “{topicName}” now. A model is reading papers to refine these matches, which takes a few minutes.
              </div>
            ) : null)}

            {following && canBuildFeed && <TopicDialog open={editingTopic} onOpenChange={setEditingTopic} />}

            {topicOnly && topic.data && (
              <div className="following-topic-note following-topic-filter" role="status">
                Showing only papers about “{topicName}”.{" "}
                <Link to={topicFilterHref(false)}>Show everything you follow</Link>
              </div>
            )}

            {showIntro ? (
              <FollowingIntro onBuild={canBuildFeed ? () => setEditingTopic(true) : undefined} />
            ) : isLoading ? (
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
            ) : cards.length === 0 ? (error ? null :
              <div className="no-results">{topicOnly ? <>No papers about your topic match these filters. Widen the date range or <button type="button" className="link-button" onClick={() => setEditingTopic(true)}>edit your topic</button>.</> : following ? <>No papers from your topic or follows match these filters. Widen the date range, or follow more from <Link to="/tasks">tasks</Link>, <Link to="/methods">methods</Link>, benchmark, author, or organization pages.</> : "No papers in this window."}</div>
            ) : (
              <>
                <div className="paper-list">
                  {cards.map((p, i) => (
                    <PaperCard key={p.id} paper={p} rank={i + 1} followReasons={p.followReasons} />
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
