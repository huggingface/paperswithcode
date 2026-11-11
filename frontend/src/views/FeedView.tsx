import FollowingIntro from "@/components/FollowingIntro";
import HomeFollowCard from "@/components/HomeFollowCard";
import TopicDialog from "@/components/TopicDialog";
import FollowBubbles, { type FeedFilter } from "@/components/FollowBubbles";
import { isAuthDisabled } from "@/lib/apiUrl";
import { clearPendingTopic, isConflict, isTopicBuilding, readPendingFollows, readPendingTopic, readPendingTopicFollows, topicTitle, useFollowTopics, useResearchFollows, useResearchTopics, useSaveFollows, useSaveTopic } from "@/lib/researchTopic";
import { useOptionalAuth } from "@/lib/authContext";
import { researchApi } from "@/lib/api/research";
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PaperFeedList, type PaperFeedCard } from "@/components/PaperFeed";
import { McpShowcase } from "@/components/McpShowcase";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { DictationButton } from "@/components/chat/DictationButton";
import { ArrowUpIcon } from "@/components/chat/icons";
import { PaperMentionHighlights } from "@/components/chat/PaperMentionHighlights";
import { PaperMentionPicker } from "@/components/chat/PaperMentionPicker";
import { completedScrollHeight, isCompletionKey, useChatCompletion } from "@/components/chat/useChatCompletion";
import { useComposerDictation } from "@/components/chat/useComposerDictation";
import { usePaperMentions } from "@/components/chat/usePaperMentions";
import { chatApi } from "@/lib/api/chat";
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
import { usePaperFeedQuery } from "@/hooks/usePapers";
import type { Paper } from "@/lib/api/papers.types";
import type { PaginatedResponse } from "@/lib/api/shared.types";
import { papersApi } from "@/lib/api/papers";
import { catalogQueries, paperFeedKeys, researchQueries } from "@/lib/api/queries";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  // Enter or Send while dictating finishes the recording, then asks.
  const sendAfterDictation = useRef(false);
  const [sendQueued, setSendQueued] = useState(false);
  const dictation = useComposerDictation({
    draft,
    onChange: setDraft,
    textareaRef: ref,
    onEnd: (cancelled) => {
      if (sendAfterDictation.current && !cancelled) setSendQueued(true);
      sendAfterDictation.current = false;
    },
  });
  const sendAfterRecording = () => {
    sendAfterDictation.current = true;
    dictation.finish();
  };
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

  useEffect(() => {
    if (!sendQueued) return;
    setSendQueued(false);
    void submit();
    // submit reads the draft rendered with the final transcript.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sendQueued]);

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
              readOnly={dictation.active}
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
                if (dictation.active) {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (dictation.phase === "recording") sendAfterRecording();
                  }
                  return;
                }
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
          {!mirror && <DictationButton dictation={dictation} disabled={launching} />}
          <button
            type="button"
            className={`chat-send${question.trim() || dictation.phase === "recording" ? " chat-send-on" : ""}`}
            onClick={() => (dictation.active ? sendAfterRecording() : void submit())}
            disabled={launching || (dictation.active ? dictation.phase !== "recording" : !question.trim())}
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
        {dictation.error && (
          <div className="chat-paper-mention-message" role="alert">{dictation.error}</div>
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

type FeedMode = "trending" | "following";

const FEED_PAGE_SIZE = 30;
// The trending feed shows the follow invitation after this many papers.
const FOLLOW_CARD_AFTER = 6;
// When the account last opened its following feed, in this browser.
const FOLLOWING_SEEN_KEY = "pwc:following-last-seen";

function readFollowingSeen(): string | null {
  try {
    return localStorage.getItem(FOLLOWING_SEEN_KEY);
  } catch {
    return null;
  }
}

function writeFollowingSeen() {
  try {
    localStorage.setItem(FOLLOWING_SEEN_KEY, new Date().toISOString());
  } catch {
    // Without storage the tab simply shows no count.
  }
}
const FOLLOWING_PAGE_SIZE = 40;

interface FeedPage {
  results: { paper: Paper; reasons?: string[]; added_at?: string | null }[];
  next_page: number | null;
}

const toFeedPage = async (request: Promise<PaginatedResponse<Paper>>): Promise<FeedPage> => {
  const page = await request;
  return { results: page.results.map((paper) => ({ paper })), next_page: page.next_page };
};

export const HomeFeed: React.FC<{ mode: FeedMode }> = ({ mode }) => {
  const following = mode === "following";
  const navigate = useNavigate();
  const auth = useOptionalAuth();
  const user = auth?.user;
  const [searchParams, setSearchParams] = useSearchParams();
  // Following defaults to its 30-day match window and trending on X to a month;
  // the trending tab defaults to a week.
  const dateRange = readHomepagePaperDateRange(searchParams, undefined, mode === "trending" ? "week" : "month");

  // The home feed only offers trending, following and trending on X; newest
  // and most cited stay on the other paper feeds.
  const showTab = (path: string) => {
    const next = new URLSearchParams(searchParams);
    next.delete("order_by");
    next.delete("only");
    next.delete("topic");
    next.delete("follow");
    const query = next.toString();
    navigate(query ? `${path}?${query}` : path);
  };

  const NO_FILTER: FeedFilter = { topicIds: [], follows: [] };
  // Each `?topic=<id>` and `?follow=<kind>:<id>` selects a bubble; the feed shows papers
  // matching any of them. `?only=topic` (older links) shows every topic's.
  const filterHref = (filter: FeedFilter) => {
    const next = new URLSearchParams(searchParams);
    next.delete("only");
    next.delete("topic");
    next.delete("follow");
    filter.topicIds.forEach(id => next.append("topic", String(id)));
    filter.follows.forEach(follow => next.append("follow", follow));
    const query = next.toString();
    return query ? `/following?${query}` : "/following";
  };

  // Sidebar: top tasks by paper count.
  const topTasks = useQuery(catalogQueries.topTasks(8));

  // Sidebar: tasks whose share of recent papers is rising vs their baseline.
  // Independent of Top Domains; overlapping entries appear in both sections
  // so neither list misrepresents its own signal.
  const trendingTasks = useQuery(catalogQueries.trendingTasks({ limit: 8, min_recent_papers: 10 }));

  const topicOnly = following && searchParams.get("only") === "topic";
  const activeFilter: FeedFilter = following ? {
    topicIds: [...new Set(searchParams.getAll("topic").map(Number).filter(Number.isInteger))],
    follows: [...new Set(searchParams.getAll("follow")
      .filter(value => /^(task|method|benchmark|author|organization):\d+$/.test(value)))],
  } : NO_FILTER;
  const filtering = activeFilter.topicIds.length > 0 || activeFilter.follows.length > 0;
  const dateFilters = { start_date: dateRange.startDate, end_date: dateRange.endDate };
  const followingFilters = { ...dateRange, topicOnly, ...activeFilter };
  // Following pages by offset; the public feeds by page number.
  const infinite = usePaperFeedQuery<FeedPage>(
    following
      ? paperFeedKeys.following(user?.hf_subject, followingFilters)
      : paperFeedKeys.trending(dateFilters),
    async (page) => {
      if (following) {
        const entries = await researchApi.following(page, followingFilters);
        const next_page = entries.length === FOLLOWING_PAGE_SIZE ? page + FOLLOWING_PAGE_SIZE : null;
        return { results: entries, next_page };
      }
      const params = { ...dateFilters, page, page_size: FEED_PAGE_SIZE, include_resources: true };
      return toFeedPage(papersApi.list({ ...params, order_by: "trending", order_dir: "desc", latest_only: true }));
    },
    { enabled: !following || !!user, initialPage: following ? 0 : 1 },
  );
  // The trending tab reads these too, to invite accounts without follows and count new papers.
  const follows = useResearchFollows();
  const topics = useResearchTopics(true, 10000);
  const hasFeed = !!follows.data?.length || !!topics.data?.length;
  const topicName = topicTitle;
  const building = topics.data?.filter(isTopicBuilding) ?? [];
  // The note names only the building topics the selected bubbles show.
  const shownBuilding = building.filter(topic => activeFilter.topicIds.length
    ? activeFilter.topicIds.includes(topic.id) : !activeFilter.follows.length);
  // The one selected topic, when it is the only bubble selected.
  const filteredTopic = activeFilter.topicIds.length === 1 && !activeFilter.follows.length
    ? topics.data?.find(topic => topic.id === activeFilter.topicIds[0]) : undefined;
  // The pop-up edits one topic (its id) or the whole feed (null); undefined while closed.
  // `?edit=1` (linked from Settings) opens it on arrival.
  const [editingTopic, setEditingTopic] = useState<number | null | undefined>(
    () => following && searchParams.get("edit") === "1" ? null : undefined,
  );
  // Refresh the feed each time a topic's backfill finishes, even while others still run.
  const queryClient = useQueryClient();
  const buildingIds = building.map(topic => topic.id).join(",");
  const wasBuilding = useRef<string[]>([]);
  useEffect(() => {
    const now = buildingIds ? buildingIds.split(",") : [];
    if (wasBuilding.current.some(id => !now.includes(id))) {
      void queryClient.invalidateQueries({ queryKey: paperFeedKeys.following(user?.hf_subject) });
    }
    wasBuilding.current = now;
  }, [buildingIds, queryClient, user?.hf_subject]);
  const noFollows = following && !!user && follows.data?.length === 0 && topics.isSuccess && topics.data.length === 0;
  const showIntro = (following && !auth?.isLoading && !user) || noFollows;
  const canBuildFeed = !!user || !isAuthDisabled();
  const showFollowCard = !following && canBuildFeed && !auth?.isLoading
    && (!user || (follows.isSuccess && topics.isSuccess && !hasFeed));
  // The "New" badge on the following tab: papers added since the following feed was last opened here.
  const [followingSeen] = useState(readFollowingSeen);
  useEffect(() => {
    if (user && (following || (hasFeed && !followingSeen))) writeFollowingSeen();
  }, [user, following, hasFeed, followingSeen]);
  const newCount = useQuery({
    ...researchQueries.followingNewCount(user?.hf_subject, followingSeen ?? ""),
    enabled: !following && !!user && hasFeed && !!followingSeen,
  });
  const newPapers = following ? 0 : newCount.data?.count ?? 0;
  // Read before this visit overwrites it, so Following can mark what arrived since.
  const markNewAfter = following && followingSeen ? Date.parse(followingSeen) : NaN;
  // The pop-up opens on its own only when the intro first shows to a visitor who arrived without follows:
  // not after a removal, and not while saving what a guest picked before signing in, which may finish
  // before follows reload. It lives here rather than in the intro so it stays open once the first save lands.
  const [hadFollows, setHadFollows] = useState(false);
  const [restoringPicks] = useState(() => !!readPendingTopic() || readPendingFollows().length > 0 || readPendingTopicFollows().length > 0);
  const [introShown, setIntroShown] = useState(false);
  if (!hadFollows && (!!topics.data?.length || !!follows.data?.length)) setHadFollows(true);
  if (showIntro && !introShown) {
    setIntroShown(true);
    if (canBuildFeed && !hadFollows && !restoringPicks) setEditingTopic(null);
  }
  // Save the topic a guest submitted before signing in; it stays stashed until the save succeeds.
  const pendingSave = useSaveTopic();
  const { mutate: savePendingTopic } = pendingSave;
  const pendingStarted = useRef(false);
  useEffect(() => {
    const pending = readPendingTopic();
    if (!user || !topics.isSuccess || !pending || pendingStarted.current) return;
    pendingStarted.current = true;
    if (topics.data.some(topic => topic.text === pending)) clearPendingTopic();
    else savePendingTopic({ text: pending });
  }, [user, topics.isSuccess, topics.data, savePendingTopic]);
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
  // Drop selected bubbles whose topic or follow is gone, e.g. after unfollowing it in the pop-up.
  const kept: FeedFilter | undefined = filtering && topics.isSuccess && follows.isSuccess ? {
    topicIds: activeFilter.topicIds.filter(id => topics.data.some(topic => topic.id === id)),
    follows: activeFilter.follows.filter(key => follows.data.some(follow => `${follow.kind}:${follow.entity_id}` === key)),
  } : undefined;
  const filterGone = !!kept && (kept.topicIds.length < activeFilter.topicIds.length
    || kept.follows.length < activeFilter.follows.length);
  useEffect(() => {
    if (filterGone && kept) navigate(filterHref(kept), { replace: true });
  });
  // And the popular topics a guest picked there; failed ones stay stashed until a retry succeeds.
  const pendingTopicFollows = useFollowTopics();
  const { mutate: followPendingTopics } = pendingTopicFollows;
  const pendingTopicFollowsStarted = useRef(false);
  useEffect(() => {
    const ids = readPendingTopicFollows();
    if (!user || !ids.length || pendingTopicFollowsStarted.current) return;
    pendingTopicFollowsStarted.current = true;
    followPendingTopics(ids);
  }, [user, followPendingTopics]);
  const cards = useMemo<PaperFeedCard[]>(
    () => infinite.data?.pages.flatMap((page) =>
      page.results.map((entry) => ({
        ...transformPaperForCard(entry.paper),
        followReasons: entry.reasons,
        isNew: !!entry.added_at && Date.parse(entry.added_at) > markNewAfter,
      })),
    ) ?? [],
    [infinite.data, markNewAfter],
  );

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
                  <button className={`sort-btn ${mode === "trending" ? "active" : ""}`} onClick={() => showTab("/")}>trending</button>
                  <button className={`sort-btn ${following ? "active" : ""}`} onClick={() => showTab("/following")}>
                    following{newPapers > 0 && <span className="nav-new-badge feed-tab-new" title="New papers since your last visit">New</span>}
                  </button>
                </div>
              </div>
              <PaperDateFilter
                startDate={dateRange.startDate}
                endDate={dateRange.endDate}
                onChange={(value) => setSearchParams(withHomepagePaperDateRange(searchParams, value))}
              />
            </div>

            {following && (!!user || !auth?.isLoading) && (
              <FollowBubbles
                topics={topics.data ?? []}
                follows={follows.data ?? []}
                active={activeFilter}
                hrefFor={filterHref}
                onEdit={canBuildFeed ? () => setEditingTopic(null) : undefined}
                editLabel={topics.data?.length || follows.data?.length ? "Edit feed" : "Build feed"}
              />
            )}

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
                  {isConflict(pendingSave.error) ? <>Could not follow “{pendingSave.variables.text}”: {pendingSave.error.message}.</>
                    : <>Could not follow “{pendingSave.variables.text}”. <button type="button" onClick={() => savePendingTopic(pendingSave.variables)}>Try again</button></>}
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

            {pendingTopicFollows.isError && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  Could not follow the popular topics you picked. <button type="button" onClick={() => followPendingTopics(readPendingTopicFollows())}>Try again</button>
                </AlertDescription>
              </Alert>
            )}

            {following && shownBuilding.length > 0 && (
              <div className="following-topic-note" role="status">
                Showing the closest papers about {shownBuilding.map(topic => `“${topicName(topic)}”`).join(" and ")} now. A model is reading papers to refine these matches, which takes a few minutes.
              </div>
            )}

            {canBuildFeed && (
              <TopicDialog
                open={editingTopic !== undefined}
                topicId={editingTopic ?? null}
                afterSavePath={following ? undefined : "/following"}
                onOpenChange={(open) => {
                  if (open) return;
                  setEditingTopic(undefined);
                  if (searchParams.has("edit")) {
                    const next = new URLSearchParams(searchParams);
                    next.delete("edit");
                    setSearchParams(next, { replace: true });
                  }
                }}
              />
            )}

            {topicOnly && !filtering && (
              <div className="following-topic-note following-topic-filter" role="status">
                Showing only papers about your topics. <Link to={filterHref(NO_FILTER)}>Show everything you follow</Link>
              </div>
            )}

            {showIntro ? (
              <FollowingIntro onBuild={canBuildFeed ? () => setEditingTopic(null) : undefined} />
            ) : (
              <PaperFeedList
                query={infinite}
                isLoading={infinite.isLoading || (following && !!auth?.isLoading)}
                cards={cards}
                skeleton="card"
                rootMargin="400px"
                cardHeader={showFollowCard ? (index) => index === FOLLOW_CARD_AFTER
                  && <HomeFollowCard onBuild={() => setEditingTopic(null)} /> : undefined}
                empty={error ? null : filteredTopic ? <>No papers about this topic match these filters. Widen the date range or <button type="button" className="link-button" onClick={() => setEditingTopic(filteredTopic.id)}>edit the topic</button>.</> : filtering ? <>No papers match the selected bubbles in this window. Widen the date range or pick more bubbles.</> : topicOnly ? <>No papers about your topics match these filters. Widen the date range or follow more topics.</> : following ? <>No papers from your topics or follows match these filters. Widen the date range, or follow more from <Link to="/tasks">tasks</Link>, <Link to="/methods">methods</Link>, benchmark, author, or organization pages.</> : "No papers in this window."}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Routes render the public feeds through this; FollowingView renders the following mode.
const FeedView: React.FC = () => (
  <HomeFeed mode="trending" />
);

export default FeedView;
