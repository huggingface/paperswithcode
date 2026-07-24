import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type ChatBlock,
  type ChatEvent,
  type ChatMessage,
  type ChatPaperHit,
  streamChat,
} from "@/lib/chat";

interface UseChatOptions {
  sessionId: string | null;
  initialModel?: string;
  onSessionId: (id: string) => void;
  onTitle: (title: string) => void;
  onSettled: () => void;
  onInterrupted: (text: string) => void;
}

export function useChat(options: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const optionsRef = useRef(options);
  const promptRef = useRef("");
  const titleRef = useRef("");
  const idRef = useRef(0);
  optionsRef.current = options;
  messagesRef.current = messages;

  useEffect(() => () => abortRef.current?.abort(), []);

  const papers = useMemo(() => {
    const map: Record<string, ChatPaperHit> = {};
    for (const message of messages) {
      for (const block of message.blocks ?? []) {
        if (block.kind === "tool") {
          for (const result of block.results ?? []) map[result.route_id] = result;
        }
      }
    }
    return map;
  }, [messages]);

  const nextId = () => `m${++idRef.current}_${Date.now().toString(36)}`;
  const patchLast = (fn: (message: ChatMessage) => ChatMessage) => setMessages((previous) => {
    if (!previous.length) return previous;
    const copy = previous.slice();
    copy[copy.length - 1] = fn(copy[copy.length - 1]);
    return copy;
  });
  const addBlock = (block: ChatBlock) => patchLast((message) => ({ ...message, blocks: [...(message.blocks ?? []), block] }));
  const patchBlock = (match: (block: ChatBlock, index: number, blocks: ChatBlock[]) => boolean, patch: (block: ChatBlock) => ChatBlock) =>
    patchLast((message) => ({ ...message, blocks: (message.blocks ?? []).map((block, index, all) => match(block, index, all) ? patch(block) : block) }));
  const isLastOfKind = (kind: ChatBlock["kind"]) => (block: ChatBlock, index: number, blocks: ChatBlock[]) =>
    block.kind === kind && blocks.findLastIndex((candidate) => candidate.kind === kind) === index;

  const applyEvent = (event: ChatEvent) => {
    switch (event.type) {
      case "stream_start":
        if (event.session_id) optionsRef.current.onSessionId(event.session_id);
        break;
      case "sandbox_start":
      case "sandbox_ready":
        break;
      case "session_title_start":
        titleRef.current = "";
        break;
      case "session_title_delta":
        titleRef.current += event.text;
        optionsRef.current.onTitle(titleRef.current.replace(/\s+/g, " ").slice(0, 80));
        break;
      case "session_title_done":
        titleRef.current = event.title;
        optionsRef.current.onTitle(event.title);
        break;
      case "reasoning_start":
        addBlock({ kind: "reasoning", text: "", active: true, open: true });
        break;
      case "reasoning_delta":
        patchBlock(isLastOfKind("reasoning"), (block) => block.kind === "reasoning" ? { ...block, text: block.text + event.text } : block);
        break;
      case "reasoning_end":
        patchBlock(isLastOfKind("reasoning"), (block) => block.kind === "reasoning" ? { ...block, active: false, open: false } : block);
        break;
      case "tool_call":
        addBlock({ kind: "tool", id: event.id, name: event.name, args: event.args, status: "running", open: false });
        break;
      case "tool_result":
        patchBlock((block) => block.kind === "tool" && block.id === event.id, (block) => block.kind === "tool"
          ? event.status
            ? { ...block, schema_version: 2, status: event.status, took_ms: event.took_ms, content: event.content, metadata: event.metadata, open: event.status !== "success" }
            : { ...block, status: "done", hits: event.hits, took_ms: event.took_ms, results: event.results }
          : block);
        break;
      case "answer_delta":
        patchLast((message) => {
          const blocks = message.blocks ?? [];
          const last = blocks.at(-1);
          if (last?.kind === "answer" && !last.done) return { ...message, blocks: [...blocks.slice(0, -1), { ...last, text: last.text + event.text }] };
          return { ...message, blocks: [...blocks, { kind: "answer", text: event.text, done: false }] };
        });
        break;
      case "done":
        patchLast((message) => ({ ...message, streaming: false, followups: event.followups, finishReason: event.finish_reason, citations: event.citations, blocks: (message.blocks ?? []).map((block) => block.kind === "answer" ? { ...block, done: true } : block) }));
        break;
      case "error":
        patchLast((message) => ({ ...message, streaming: false, error: event.message }));
        break;
    }
  };

  const send = useCallback((text: string) => {
    const question = text.trim();
    if (!question || busyRef.current) return false;
    busyRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    promptRef.current = question;
    const latestUser = [...messagesRef.current].reverse().find((message) => message.role === "user");
    const replacement = latestUser?.status && latestUser.status !== "complete" && latestUser.revision
      ? { replace_message_id: latestUser.id, prior_revision: latestUser.revision }
      : null;
    setMessages((previous) => {
      const nextUser: ChatMessage = { id: nextId(), role: "user", text: question };
      const nextAssistant: ChatMessage = { id: nextId(), role: "assistant", streaming: true, blocks: [] };
      if (!replacement) return [...previous, nextUser, nextAssistant];
      const replaceIndex = previous.findLastIndex((message) => message.id === latestUser.id);
      return replaceIndex < 0
        ? [...previous, nextUser, nextAssistant]
        : [...previous.slice(0, replaceIndex), nextUser, nextAssistant];
    });
    setBusy(true);
    void (async () => {
      try {
        for await (const event of streamChat({
          message: question,
          session_id: optionsRef.current.sessionId,
          client_message_id: crypto.randomUUID(),
          ...(!optionsRef.current.sessionId && optionsRef.current.initialModel ? { initial_model: optionsRef.current.initialModel } : {}),
          ...(replacement ?? {}),
        }, { signal: controller.signal })) {
          if (!controller.signal.aborted) applyEvent(event);
        }
      } catch (error) {
        if (!controller.signal.aborted) applyEvent({ type: "error", message: error instanceof Error ? error.message : "The assistant stream failed." });
      } finally {
        if (abortRef.current === controller) {
          busyRef.current = false;
          setBusy(false);
          patchLast((message) => message.streaming ? { ...message, streaming: false } : message);
          optionsRef.current.onSettled();
        }
      }
    })();
    return true;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useCallback(() => {
    if (!abortRef.current) return;
    abortRef.current.abort();
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    setMessages((previous) => {
      const last = previous.at(-1);
      if (last?.role !== "assistant") return previous;
      const completed = (last.blocks ?? []).flatMap((block): ChatBlock[] => {
        if (block.kind === "tool" && block.status === "running") return [];
        if (block.kind === "reasoning" && block.active) return [];
        if (block.kind === "answer") return [{ ...block, done: true }];
        return [block];
      });
      return [
        ...previous.slice(0, -1),
        { ...last, blocks: completed, streaming: false, finishReason: "stopped" },
      ];
    });
    optionsRef.current.onInterrupted(promptRef.current);
    window.setTimeout(optionsRef.current.onSettled, 250);
  }, []);

  const toggleBlock = useCallback((messageId: string, blockIndex: number) => setMessages((previous) => previous.map((message) => message.id !== messageId ? message : { ...message, blocks: message.blocks?.map((block, index) => index === blockIndex && (block.kind === "reasoning" || block.kind === "tool") ? { ...block, open: !block.open } : block) })), []);
  const reset = useCallback(() => { abortRef.current?.abort(); abortRef.current = null; busyRef.current = false; setMessages([]); setBusy(false); }, []);
  const load = useCallback((restored: ChatMessage[]) => { abortRef.current?.abort(); abortRef.current = null; busyRef.current = false; setMessages(restored); setBusy(false); }, []);

  return { messages, busy, papers, send, stop, toggleBlock, reset, load };
}
