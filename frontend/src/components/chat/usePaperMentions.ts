import { useQuery } from "@tanstack/react-query";
import React from "react";

import type { Paper } from "@/lib/api/papers.types";
import { chatApi } from "@/lib/api/chat";
import { papersApi } from "@/lib/api/papers";
import type { ChatDraft, PaperMentionDraft } from "@/lib/chat";
import { withDraftText } from "@/lib/paperSelection";

const MAX_PAPER_MENTIONS = 10;
const MAX_DISTINCT_PAPERS = 3;

interface ActiveMention { start: number; end: number; query: string }

export function activePaperMention(text: string, caret: number): ActiveMention | null {
  const before = text.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  const preceding = at > 0 ? text[at - 1] : "";
  if (preceding && /[\p{L}\p{M}\p{N}_@]/u.test(preceding)) return null;
  const query = text.slice(at + 1, caret);
  if (/[\n\r@]/.test(query)) return null;
  return { start: at, end: caret, query };
}

export function reconcilePaperMentions(
  previous: string,
  next: string,
  mentions: PaperMentionDraft[],
): PaperMentionDraft[] {
  let prefix = 0;
  while (prefix < previous.length && prefix < next.length && previous[prefix] === next[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < previous.length - prefix
    && suffix < next.length - prefix
    && previous[previous.length - 1 - suffix] === next[next.length - 1 - suffix]
  ) suffix += 1;
  const previousEnd = previous.length - suffix;
  const delta = next.length - previous.length;
  return mentions.flatMap((mention) => {
    if (mention.end <= prefix) return [mention];
    if (mention.start >= previousEnd) return [{ ...mention, start: mention.start + delta, end: mention.end + delta }];
    return [];
  });
}

interface UsePaperMentionsOptions {
  draft: ChatDraft;
  onChange: (draft: ChatDraft) => void;
  enabled: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}

export function usePaperMentions({ draft, onChange, enabled, textareaRef }: UsePaperMentionsOptions) {
  const pickerId = `chat-paper-picker-${React.useId().replace(/:/g, "")}`;
  const optionIdPrefix = `${pickerId}-option`;
  const [active, setActive] = React.useState<ActiveMention | null>(null);
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [message, setMessage] = React.useState("");
  const prewarmed = React.useRef(new Set<string>());

  React.useEffect(() => {
    if (!enabled) setActive(null);
  }, [enabled]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(active?.query.trim() ?? ""), 150);
    return () => window.clearTimeout(timer);
  }, [active?.query]);

  const search = useQuery({
    queryKey: ["chat-paper-mention-search", debouncedQuery.toLowerCase()],
    queryFn: ({ signal }) => papersApi.search(debouncedQuery, 1, 10, "hybrid", signal),
    enabled: enabled && Boolean(active) && debouncedQuery.length >= 1,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const results = React.useMemo(() => search.data?.results ?? [], [search.data?.results]);

  React.useEffect(() => setActiveIndex(0), [debouncedQuery]);
  React.useEffect(() => {
    document.getElementById(`${optionIdPrefix}-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, optionIdPrefix]);

  const refresh = React.useCallback((caret?: number) => {
    if (!enabled) { setActive(null); return; }
    const position = caret ?? textareaRef.current?.selectionStart ?? draft.text.length;
    if (draft.paperMentions.some((mention) => position > mention.start && position <= mention.end)) {
      setActive(null);
      return;
    }
    setActive(activePaperMention(draft.text, position));
  }, [draft.paperMentions, draft.text, enabled, textareaRef]);

  const updateText = React.useCallback((next: string, caret?: number) => {
    const mentions = reconcilePaperMentions(draft.text, next, draft.paperMentions);
    const nextDraft = withDraftText(draft, next, mentions);
    onChange(nextDraft);
    const position = caret ?? textareaRef.current?.selectionStart ?? next.length;
    if (enabled && !mentions.some((mention) => position > mention.start && position <= mention.end)) {
      setActive(activePaperMention(next, position));
    } else {
      setActive(null);
    }
  }, [draft, enabled, onChange, textareaRef]);

  const select = React.useCallback((paper: Paper): boolean => {
    if (!active) return false;
    const routeId = paper.arxiv_id || paper.id;
    const distinct = new Set(draft.paperMentions.map((mention) => mention.route_id));
    if (draft.paperMentions.length >= MAX_PAPER_MENTIONS) {
      setMessage("A message can contain at most 10 paper mentions.");
      return false;
    }
    if (!distinct.has(routeId) && distinct.size >= MAX_DISTINCT_PAPERS) {
      setMessage("A message can attach at most 3 distinct papers.");
      return false;
    }
    // The leading @ is the search trigger, not part of the committed marker.
    // Once selected, the structured range is sufficient to retain identity.
    const marker = paper.title;
    const suffix = draft.text.slice(active.end);
    const appendSpace = suffix.length === 0;
    const nextText = draft.text.slice(0, active.start) + marker + (appendSpace ? " " : "") + suffix;
    const shifted = reconcilePaperMentions(draft.text, nextText, draft.paperMentions);
    const mention: PaperMentionDraft = {
      key: crypto.randomUUID(),
      route_id: routeId,
      title: paper.title,
      source: paper.source === "external" ? "external" : "arxiv",
      start: active.start,
      end: active.start + marker.length,
    };
    onChange(withDraftText(draft, nextText, [...shifted, mention].sort((a, b) => a.start - b.start)));
    setActive(null);
    setMessage("");
    window.requestAnimationFrame(() => {
      const caret = mention.end + (appendSpace || suffix.startsWith(" ") ? 1 : 0);
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(caret, caret);
    });
    if (!prewarmed.current.has(routeId)) {
      prewarmed.current.add(routeId);
      void chatApi.prewarmPaperContext(routeId).catch(() => undefined);
    }
    return true;
  }, [active, draft, onChange, textareaRef]);

  const keyDown = React.useCallback((event: React.KeyboardEvent<HTMLTextAreaElement>): boolean => {
    if (!active || event.nativeEvent.isComposing) return false;
    if (event.key === "Tab") { setActive(null); return false; }
    if (event.key === "Escape") { event.preventDefault(); setActive(null); return true; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (results.length) setActiveIndex((index) => (
        event.key === "ArrowDown" ? (index + 1) % results.length : (index - 1 + results.length) % results.length
      ));
      return true;
    }
    if (event.key === "Home" && results.length) { event.preventDefault(); setActiveIndex(0); return true; }
    if (event.key === "End" && results.length) { event.preventDefault(); setActiveIndex(results.length - 1); return true; }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (results[activeIndex]) select(results[activeIndex]);
      else if (!search.isFetching) setActive(null);
      return true;
    }
    return false;
  }, [active, activeIndex, results, search.isFetching, select]);

  return {
    open: Boolean(active), query: active?.query ?? "", results, activeIndex,
    loading: search.isFetching, error: search.isError, message,
    pickerId, optionIdPrefix,
    updateText, refresh, select, keyDown, close: () => setActive(null),
  };
}
